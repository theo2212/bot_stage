from abc import ABC, abstractmethod

class BaseScraper(ABC):
    def __init__(self):
        self.results = []

    @abstractmethod
    def search(self, query: str, location: str):
        """
        Search for jobs based on query and location.
        """
        pass

    def get_results(self):
        """
        Return results as a list of dictionaries.
        """
        return self.results
