from .config import HPackageConfig
from .step import Step

class Stage:
    def __init__(self, config: HPackageConfig, package, package_name: str):
        self.config = config
        self.package_name = package_name
        self.package = package

        source_properties = config.pkgsrc_yml

        self.name = source_properties["name"]

        if "tools-required" in source_properties:
            self.tools_required = source_properties["tools-required"]
        else:
            self.tools_required = []
        
        if "pkgs-required" in source_properties:
            self.pkgs_required = source_properties["pkgs-required"]
        else:
            self.pkgs_required = []

        self.compile_ymls: list[dict[str, str]] = []
        self.install_ymls: list[dict[str, str]] = []
        self.build_ymls: list[dict[str, str]] = []

        self.compile_steps: list[Step] = []
        self.install_steps: list[Step] = []
        self.build_steps: list[Step] = []

        if "compile" in source_properties:
            configure_properties = source_properties["compile"]
            for step_yml in configure_properties:
                self.compile_ymls.append(step_yml)

        if "install" in source_properties:
            configure_properties = source_properties["install"]
            for step_yml in configure_properties:
                self.install_ymls.append(step_yml)

        if "build" in source_properties:
            build_properties = source_properties["build"]
            for step_yml in build_properties:
                self.build_ymls.append(step_yml)
    
    def deps(self):
        deps = []
        for tool in self.tools_required:
            if isinstance(tool, dict):
                if "stage-dependencies" in tool:
                    for stage_dep in tool["stage-dependencies"]:
                        deps.append(f"{tool['tool']}[{stage_dep}]")
                else:
                    deps.append(tool["tool"])
            else:
                deps.append(tool)

        for pkg in self.pkgs_required:
            deps.append(pkg)
        
        return deps
    
    def __str__(self):
        return f"Stage {self.name}: {self.tools_required}, {self.pkgs_required}"
    
    def __repr__(self):
        return self.__str__()