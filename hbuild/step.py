from enum import Enum
import multiprocessing
import os
import subprocess

class StepWorkdirType(Enum):
    CUSTOM = 1
    BUILDDIR = 2

class Step:
    def __init__(self, source_data, package):
        source_properties = source_data

        self.args: list[str] = source_properties["args"]
        self.cpu_count = multiprocessing.cpu_count()

        self.package = package

        if "workdir" in source_properties:
            self.workdir_type = StepWorkdirType.CUSTOM
            self.workdir: str = source_properties["workdir"]
        else:
            self.workdir_type = StepWorkdirType.BUILDDIR
            self.workdir: str = self.package.dir

        if "environ" in source_properties:
            self.environ: dict[str, str] = source_properties["environ"]
        else:
            self.environ: dict[str, str] = {}

        if "shell" in source_properties:
            self.shell = True
        else:
            self.shell = False

    def do_substitutions(self, system_prefix, system_target,  source_dir, build_dir, system_dir):
        replaced_args = []
        replaced_environ: dict[str, str]= {}
        if self.workdir_type == StepWorkdirType.BUILDDIR:
            replaced_workdir = os.path.join(build_dir, self.workdir)
        else:
            replaced_workdir = self.workdir

        source_dir = os.path.join(source_dir, self.package.source_dir)
        source_root = source_dir

        collect_dir = os.path.join(build_dir, self.package.dir)

        sysroot_dir = system_dir
        prefix_dir = system_prefix

        parallelism = self.cpu_count

        for arg in self.args:
            arg = arg.replace("@THIS_SOURCE_DIR@", source_dir)
            arg = arg.replace("@THIS_COLLECT_DIR@", collect_dir)

            arg = arg.replace("@SOURCE_ROOT@", source_root)
            arg = arg.replace("@SYSROOT_DIR@", sysroot_dir)

            arg = arg.replace("@PREFIX@", prefix_dir)
            arg = arg.replace("@TARGET@", system_target)
            arg = arg.replace("@PARALLELISM@", str(parallelism))

            replaced_args.append(arg)

        for env_var, env_val in self.environ.items():
            env_val = env_val.replace("@THIS_SOURCE_DIR@", source_dir)
            env_val = env_val.replace("@THIS_COLLECT_DIR@", collect_dir)

            env_val = env_val.replace("@SOURCE_ROOT@", source_root)
            env_val = env_val.replace("@SYSROOT_DIR@", sysroot_dir)

            env_val = env_val.replace("@PREFIX@", prefix_dir)
            env_val = env_val.replace("@TARGET@", system_target)
            env_val = env_val.replace("@PARALLELISM@", str(parallelism))

            replaced_environ[env_var] = env_val     

        replaced_workdir = replaced_workdir.replace("@THIS_SOURCE_DIR@", source_dir)
        replaced_workdir = replaced_workdir.replace("@THIS_COLLECT_DIR@", collect_dir)

        replaced_workdir = replaced_workdir.replace("@SOURCE_ROOT@", source_root)
        replaced_workdir = replaced_workdir.replace("@SYSROOT_DIR@", sysroot_dir)

        replaced_workdir = replaced_workdir.replace("@PREFIX@", prefix_dir)
        replaced_workdir = replaced_workdir.replace("@TARGET@", system_target)
        replaced_workdir = replaced_workdir.replace("@PARALLELISM@", str(parallelism))

        if "PATH" in replaced_environ:
            replaced_environ['PATH'] = f"{replaced_environ['PATH']}:{collect_dir}:$PATH"
        else:
            replaced_environ['PATH'] = f"{collect_dir}:$PATH"

        return replaced_args, replaced_environ, replaced_workdir

    def exec(self, system_prefix, system_target,  source_dir, build_dir, system_dir):
        args, environ, workdir = self.do_substitutions(system_prefix, system_target, source_dir, build_dir, system_dir)
        
        res = subprocess.run(args, env = environ, cwd = workdir, shell = self.shell, 
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
        
        print(res.stdout)
        
    def __str__(self):
        return f"Step: {self.environ} {self.args}: {self.workdir}"

    def __repr__(self):
        return self.__str__()