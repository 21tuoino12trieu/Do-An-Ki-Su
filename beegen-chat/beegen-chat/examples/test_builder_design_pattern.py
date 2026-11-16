from abc import ABC, abstractmethod
from typing import Any, Optional


class Computer:
    """The complex object being built"""
    
    def __init__(self):
        self.cpu: Optional[str] = None
        self.memory: Optional[int] = None
        self.storage: Optional[int] = None
        self.gpu: Optional[str] = None
        self.os: Optional[str] = None
        self.monitor: Optional[str] = None
        self.keyboard: Optional[str] = None
        self.mouse: Optional[str] = None
    
    def __str__(self) -> str:
        components = []
        if self.cpu:
            components.append(f"CPU: {self.cpu}")
        if self.memory:
            components.append(f"RAM: {self.memory}GB")
        if self.storage:
            components.append(f"Storage: {self.storage}GB")
        if self.gpu:
            components.append(f"GPU: {self.gpu}")
        if self.os:
            components.append(f"OS: {self.os}")
        if self.monitor:
            components.append(f"Monitor: {self.monitor}")
        if self.keyboard:
            components.append(f"Keyboard: {self.keyboard}")
        if self.mouse:
            components.append(f"Mouse: {self.mouse}")
        
        return "Computer Specifications:\n- " + "\n- ".join(components)


class ComputerBuilder(ABC):
    """Abstract Builder interface"""
    
    @abstractmethod
    def reset(self) -> None:
        pass
    
    @abstractmethod
    def build_cpu(self, cpu: str) -> None:
        pass
    
    @abstractmethod
    def build_memory(self, size_gb: int) -> None:
        pass
    
    @abstractmethod
    def build_storage(self, size_gb: int) -> None:
        pass
    
    @abstractmethod
    def build_gpu(self, gpu: str) -> None:
        pass
    
    @abstractmethod
    def build_os(self, os: str) -> None:
        pass
    
    @abstractmethod
    def build_monitor(self, monitor: str) -> None:
        pass
    
    @abstractmethod
    def build_keyboard(self, keyboard: str) -> None:
        pass
    
    @abstractmethod
    def build_mouse(self, mouse: str) -> None:
        pass
    
    @abstractmethod
    def get_computer(self) -> Computer:
        pass


class StandardComputerBuilder(ComputerBuilder):
    """Concrete Builder implementation"""
    
    def __init__(self):
        self.reset()
    
    def reset(self) -> None:
        self._computer = Computer()
    
    def build_cpu(self, cpu: str) -> None:
        self._computer.cpu = cpu
    
    def build_memory(self, size_gb: int) -> None:
        self._computer.memory = size_gb
    
    def build_storage(self, size_gb: int) -> None:
        self._computer.storage = size_gb
    
    def build_gpu(self, gpu: str) -> None:
        self._computer.gpu = gpu
    
    def build_os(self, os: str) -> None:
        self._computer.os = os
    
    def build_monitor(self, monitor: str) -> None:
        self._computer.monitor = monitor
    
    def build_keyboard(self, keyboard: str) -> None:
        self._computer.keyboard = keyboard
    
    def build_mouse(self, mouse: str) -> None:
        self._computer.mouse = mouse
    
    def get_computer(self) -> Computer:
        result = self._computer
        self.reset()
        return result


class Director:
    """Director class that controls the construction process"""
    
    def __init__(self, builder: ComputerBuilder):
        self._builder = builder
    
    def change_builder(self, builder: ComputerBuilder) -> None:
        self._builder = builder
    
    def make_gaming_pc(self) -> None:
        self._builder.reset()
        self._builder.build_cpu("Intel Core i9-13900K")
        self._builder.build_memory(32)
        self._builder.build_storage(2000)
        self._builder.build_gpu("NVIDIA RTX 4090")
        self._builder.build_os("Windows 11")
        self._builder.build_monitor("27-inch 4K Gaming Monitor")
        self._builder.build_keyboard("RGB Mechanical Keyboard")
        self._builder.build_mouse("Gaming Mouse with 16000 DPI")
    
    def make_office_pc(self) -> None:
        self._builder.reset()
        self._builder.build_cpu("Intel Core i5-12400")
        self._builder.build_memory(16)
        self._builder.build_storage(512)
        self._builder.build_gpu("Integrated Graphics")
        self._builder.build_os("Windows 11")
        self._builder.build_monitor("24-inch 1080p Monitor")
        self._builder.build_keyboard("Standard Keyboard")
        self._builder.build_mouse("Standard Mouse")
    
    def make_developer_workstation(self) -> None:
        self._builder.reset()
        self._builder.build_cpu("AMD Ryzen 9 7950X")
        self._builder.build_memory(64)
        self._builder.build_storage(4000)
        self._builder.build_gpu("NVIDIA RTX 4080")
        self._builder.build_os("Ubuntu Linux 22.04")
        self._builder.build_monitor("Dual 27-inch 4K Monitors")
        self._builder.build_keyboard("Ergonomic Mechanical Keyboard")
        self._builder.build_mouse("Programmable Mouse")


# Client code
if __name__ == "__main__":
    # Using the builder directly
    builder = StandardComputerBuilder()
    
    builder.build_cpu("Intel Core i7-13700K")
    builder.build_memory(16)
    builder.build_storage(1000)
    builder.build_gpu("NVIDIA RTX 4070")
    builder.build_os("Windows 11")
    custom_pc = builder.get_computer()
    
    print("Custom PC:")
    print(custom_pc)
    print("\n" + "-" * 50 + "\n")
    
    # Using the director
    director = Director(builder)
    
    # Build a gaming PC
    director.make_gaming_pc()
    gaming_pc = builder.get_computer()
    
    print("Gaming PC:")
    print(gaming_pc)
    print("\n" + "-" * 50 + "\n")
    
    # Build an office PC
    director.make_office_pc()
    office_pc = builder.get_computer()
    
    print("Office PC:")
    print(office_pc)
    print("\n" + "-" * 50 + "\n")
    
    # Build a developer workstation
    director.make_developer_workstation()
    dev_workstation = builder.get_computer()
    
    print("Developer Workstation:")
    print(dev_workstation)