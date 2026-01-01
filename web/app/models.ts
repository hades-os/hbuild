type HBuildState = "unbuilt" | "configured" | "built" | "installed"
type HBuildPackageType = "package" | "tool" | "source"

type StageStatus = {
    stage_name: string,
    name: string,
    package: string,

    status: HBuildState
}

type PackageStatus = {
    name: string,
    type: HBuildPackageType,
    status: HBuildState,
    stages?: StageStatus[]
}

type PackageStatusList = {
    packages: PackageStatus[]
}

export type {
    PackageStatusList,
    HBuildState,
    HBuildPackageType
}