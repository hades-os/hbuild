from .registry import HPackageRegistry
from .dispatch import HBuildDispatch

if __name__ == '__main__':
    dispatch = HBuildDispatch()
    dispatch.run_server()