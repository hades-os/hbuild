from .step import Step

class Stage:
    def __init__(self, source_data, tool_package):
        source_properties = source_data

        self.name = source_properties["name"]
        self.dir = tool_package.dir
        self.source_dir = tool_package.source_dir

        if "tools-required" in source_properties:
            self.tools_required = source_properties["tools-required"]
        else:
            self.tools_required = []
        
        if "pkgs-required" in source_properties:
            self.pkgs_required = source_properties["pkgs-required"]
        else:
            self.pkgs_required = []

        self.compile_steps: list[Step] = []
        if "compile" in source_properties:
            compile_properties = source_properties["compile"]
            for step in compile_properties:
                self.compile_steps.append(Step(step, self))

        self.install_steps: list[Step] = []
        if "install" in source_properties:
            install_properties = source_properties["install"]
            for step in install_properties:
                self.install_steps.append(Step(step, self))

        self.build_steps: list[Step] = []
        if "build" in source_properties:
            build_properties = source_properties["build"]
            for step in build_properties:
                self.build_steps.append(Step(step, self))
    
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