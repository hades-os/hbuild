type HBuildState = "unbuilt" | "configured" | "built" | "installed"
type HBuildPackageType = "package" | "tool" | "source"

type StageStatus = {
    stage_name: string,
    name: string,
    package: string,

    status: HBuildState
}

type PackageGraphEdge = {
    source: string;
    dest: string;
}

type PackageGraph = {
    nodes: string[];
    edges: PackageGraphEdge[]
}

type PackageInfo = {
    name: string,
    type: HBuildPackageType,
    stages?: StageStatus[]
}

type PackageInfoList = {
    packages: PackageInfo[]
}

type PackageHistoryEntry = {
    id: number,
    runner: string,
    packages: string[],
    created_at: number
}

type PackageHistoryList = {
    past_jobs: PackageHistoryEntry[]
}

type LogEvent = {
    id: number;
    package: string;
    stage: string;
    log: string;
    created_at: string;
}

type LogEventStream = {
    logs: LogEvent[]
}

export type {
    PackageInfoList,
    PackageInfo,

    PackageHistoryList,
    PackageHistoryEntry

    HBuildState,
    HBuildPackageType,

    LogEvent,
    LogEventStream,

    PackageGraphEdge,
    PackageGraph
}