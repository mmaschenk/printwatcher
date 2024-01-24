from abc import abstractmethod, ABCMeta
import requests

class LightController(metaclass=ABCMeta):
    @abstractmethod
    def lights(self, status):
        pass

class WLEDController(LightController):

    def __init__(self, address) -> None:
        super().__init__()
        self.address = address
        self.base = f"http://{address}/json"

    def _postdata(self, data):
        setstate = f"{self.base}/state"
        r = requests.post(setstate, json=data, headers={"Content-Type": "application/json"})
        return r

    def lights(self, status):
        return self._postdata({"on": status})

    def getstate(self):
        getstate = f"{self.base}/state"
        r = requests.get(url=getstate)
        return r.json()
    
    def savestate(self):
        s = self.getstate()
        self._savedstate = s

    def restorestate(self):
        self._postdata(self._savedstate)

def maintest():
    print("Here we go")

if __name__ == '__main__':
    maintest()