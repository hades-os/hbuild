type HBuildState = "unbuilt" | "configured" | "built" | "installed"
type HBuildPackageType = "package" | "tool" | "source"

type StageStatus = {
    stage_name: string,
    name: string,
    package: string,

    status: HBuildState
}

type PackageInfo = {
    name: string,
    type: HBuildPackageType,
    stages?: StageStatus[]
}

type PackageInfoList = {
    packages: PackageInfo[]
}

type ServerSentEvent = {
    id: string;
    event: string;
    data: string;
    retry?: number;
}

export type {
    PackageInfoList,
    PackageInfo,
    HBuildState,
    HBuildPackageType,

    ServerSentEvent
}