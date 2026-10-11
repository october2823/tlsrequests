from setuptools import setup
from setuptools.dist import Distribution
from wheel.bdist_wheel import bdist_wheel


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


class BinaryWheel(bdist_wheel):
    def finalize_options(self):
        super().finalize_options()
        self.root_is_pure = False


setup(distclass=BinaryDistribution, cmdclass={"bdist_wheel": BinaryWheel})
