import numpy
from setuptools import setup, Extension

voice_ext = Extension(
    "voice_separation",
    sources=["voice_separation.c", "voice_separation_module.c"],
    include_dirs=[numpy.get_include()],
)

setup(
    name="voice_separation",
    version="0.0",
    install_requires=["numpy"],
    ext_modules=[voice_ext],
)
