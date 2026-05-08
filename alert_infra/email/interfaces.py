from abc import ABC, abstractmethod

class EmailProvider(ABC):
    name: str

    @abstractmethod
    def send(self, to, subject, html, text):
        pass


