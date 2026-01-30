from pathlib import Path

class HPackageConfig:
    def __init__(self, logs_dir: Path, sources_dir: Path, source_dir: Path, patches_dir: Path,
                 system_targets: list[str], system_prefix: Path, system_root: Path,
                 tools_dir: Path, packages_dir: Path, builds_dir: Path, works_dir: Path,
                 pkgsrc_yml: dict[str, str]):
        self.logs_dir = logs_dir
        self.sources_dir = sources_dir.resolve().as_posix()
        self.source_dir = None
        self.patches_dir = patches_dir.resolve().as_posix()
        self.system_targets = system_targets
        self.system_prefix = system_prefix.resolve().as_posix()
        self.system_root = system_root.resolve().as_posix()
        self.tools_dir = tools_dir.resolve().as_posix()
        self.packages_dir = packages_dir.resolve().as_posix()
        self.builds_dir = builds_dir.resolve().as_posix()
        self.works_dir = works_dir.resolve().as_posix()
        self.pkgsrc_yml = pkgsrc_yml