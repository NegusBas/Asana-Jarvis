import docker
import psutil
import logging

class DockerManager:
    def __init__(self):
        try:
            self.client = docker.from_env()
        except Exception as e:
            logging.error(f"Failed to connect to Docker daemon: {e}")
            self.client = None

    def list_containers(self, all=False):
        """Lists running or all containers."""
        if not self.client:
            return "Error: Docker not connected."
        try:
            containers = self.client.containers.list(all=all)
            if not containers:
                return "No containers found."
            
            result = []
            for c in containers:
                result.append({
                    "id": c.short_id,
                    "name": c.name,
                    "status": c.status,
                    "image": c.image.tags[0] if c.image.tags else "unknown"
                })
            return result
        except Exception as e:
            return f"Error listing containers: {e}"

    def control_service(self, service_name, action):
        """Starts or stops a specific service."""
        if not self.client:
            return "Error: Docker not connected."
        try:
            container = self.client.containers.get(service_name)
            if action == "start":
                container.start()
                return f"Service {service_name} started successfully."
            elif action == "stop":
                container.stop()
                return f"Service {service_name} stopped successfully."
            else:
                return f"Unknown action: {action}"
        except docker.errors.NotFound:
            return f"Service {service_name} not found."
        except Exception as e:
            return f"Error controlling service {service_name}: {e}"

    def get_system_resources(self):
        """Reports on CPU and RAM usage."""
        cpu_usage = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Docker specific resource usage
        docker_cpu = 0.0
        docker_mem = 0.0
        if self.client:
            try:
                for container in self.client.containers.list():
                    stats = container.stats(stream=False)
                    # Simple calculation for CPU and Memory
                    # Note: stats['cpu_stats']['cpu_usage']['total_usage'] needs delta for actual %
                    # For simplicity, we just report memory here.
                    mem_usage = stats['memory_stats'].get('usage', 0) / (1024 * 1024) # MB
                    docker_mem += mem_usage
            except:
                pass

        return {
            "total_cpu_percent": cpu_usage,
            "total_ram_used_gb": round(memory.used / (1024**3), 2),
            "total_ram_available_gb": round(memory.available / (1024**3), 2),
            "docker_ram_usage_mb": round(docker_mem, 2)
        }
