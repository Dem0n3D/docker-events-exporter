import docker
import os

from prometheus_client import start_http_server, Counter


swarm_events = Counter('docker_swarm_events',
                       'Docker Swarm events',
                       ['type', 'action', 'stack', 'service', 'node', 'exit'])


def watch():
    client = docker.DockerClient(version='auto', base_url=os.getenv('DOCKER_SOCKET', 'unix://var/run/docker.sock'))
    for event in client.events(decode=True):
        attributes = event['Actor']['Attributes']
        if 'com.docker.swarm.service.name' in attributes and event['Type'] == 'container':
            swarm_events.labels(type=event['Type'],
                                action=event['Action'],
                                stack=attributes.get('com.docker.stack.namespace'),
                                service=attributes['com.docker.swarm.service.name'],
                                node=attributes['com.docker.swarm.node.id'],
                                exit=attributes.get('exitCode', 0))\
                .inc()


if __name__ == '__main__':
    port = os.getenv('PROMETHEUS_PORT', 9000)
    print(f'Start prometheus client on port {port}')
    start_http_server(port, addr=os.getenv('PROMETHEUS_LISTEN_ADDRESS', '0.0.0.0'))
    watch()
