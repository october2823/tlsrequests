from setuptools import setup
from wheel.bdist_wheel import bdist_wheel

class BinaryWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        from sysconfig import get_platform
        platform = self.plat_name or get_platform()
        return "py3", "none", platform.replace("-", "_")

setup(cmdclass={"bdist_wheel": BinaryWheel})
