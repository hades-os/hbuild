from enum import Enum, StrEnum
from pydantic import BaseModel

class HBuildState(StrEnum):
    CONFIGURED = 'configured'
    BUILT = 'built'
    INSTALLED = 'installed'

class HBuildTo(StrEnum):
    CLEAN = 'clean'
    BUILD = 'build'
    INSTALL = 'install'
    PACKAGE = 'package'

class BuildItem(BaseModel):
    name: str
    stage: str | None = None

class BuildOrder(BaseModel):
    build_to:  HBuildTo
    packages: list[BuildItem]

class ResolveOrder(BaseModel):
    packages: list[str]