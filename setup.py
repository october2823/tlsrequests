from setuptools import setup
from wheel.bdist_wheel import bdist_wheel

class BinaryWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False


setup(cmdclass={"bdist_wheel": BinaryWheel})
