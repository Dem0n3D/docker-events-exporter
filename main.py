import datetime
import docker
import queue
import os
import threading
import time

from itertools import groupby
from operator import itemgetter
from prometheus_client import start_http_server, Counter, Gauge, Enum


docker_client = docker.DockerClient(version='auto', base_url=os.getenv('DOCKER_SOCKET', 'unix://var/run/docker.sock'))


container_events = Counter('docker_container_events',
                           'Docker Container Events',
                           ['type', 'action', 'stack', 'service', 'node', 'exit'])

docker_services_last_update_seconds = Gauge('docker_swarm_services_task_last_update_seconds',
                                            'Docker Swarm Service task last update timestamp',
                                            ['service', 'slot'])

docker_services_state = Enum('docker_swarm_service_task_state',
                             'Docker Swarm service task state',
                             ['service', 'slot'],
                             states=[
                                 'new',
                                 'pending',
                                 'assigned',
                                 'accepted',
                                 # 'preparing',
                                 'starting',
                                 'running',
                                 'complete',
                                 'failed',
                                 'shutdown',
                                 'rejected',
                                 'orphaned',
                                 'remove',
                                 # 'ready',
                             ])

exc_q = queue.Queue()


def watch_docker_events():
    for event in docker_client.events(decode=True):
        attributes = event['Actor']['Attributes']
        if 'com.docker.swarm.service.name' in attributes and event['Type'] == 'container':
            container_events.labels(type=event['Type'],
                                    action=event['Action'],
                                    stack=attributes.get('com.docker.stack.namespace'),
                                    service=attributes['com.docker.swarm.service.name'],
                                    node=attributes['com.docker.swarm.node.id'],
                                    exit=attributes.get('exitCode', 0))\
                .inc()


def watch_swarm_events():
    while True:
        docker_services_last_update_seconds.clear()
        docker_services_state.clear()

        for service in docker_client.services.list(filters={'mode': 'replicated'}):
            for slot, tasks in groupby(sorted(service.tasks(), key=itemgetter('Slot', 'CreatedAt'), reverse=True),
                                       key=itemgetter('Slot')):
                tasks = list(tasks)
                if tasks:
                    docker_services_last_update_seconds.labels(service=service.name, slot=slot)\
                        .set(datetime.datetime.fromisoformat(tasks[0]['CreatedAt'].split('.')[0]).timestamp())
                for task in tasks:
                    # latest task for this slot not in preparing or ready state
                    if task['Status']['State'] not in ['preparing', 'ready']:
                        docker_services_state.labels(service=service.name, slot=slot).state(task['Status']['State'])
                        break

        time.sleep(int(os.getenv('SWARM_INTERVAL_SECONDS', 10)))


def thread_exc_wrapper(f):
    def wrapper():
        try:
            f()
        except Exception as e:
            exc_q.put(e)

    return wrapper


if __name__ == '__main__':
    port = int(os.getenv('PROMETHEUS_PORT', 9000))
    print(f'Start prometheus client on port {port}')
    start_http_server(port, addr=os.getenv('PROMETHEUS_LISTEN_ADDRESS', '0.0.0.0'))
    threading.Thread(target=thread_exc_wrapper(watch_swarm_events), daemon=True).start()
    threading.Thread(target=thread_exc_wrapper(watch_docker_events), daemon=True).start()
    raise exc_q.get(True)
