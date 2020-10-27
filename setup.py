import setuptools

setuptools.setup(
    name="easyfix",
    version="0.1.3",
    author="Chris Yuen",
    author_email="chris@kizzx2.com",
    long_description=open('README.md', 'r').read(),
    long_description_content_type='text/markdown',
    url="https://github.com/kizzx2/easyfix",
    install_requires=["lxml", "loguru"],
    packages=setuptools.find_packages(),
    include_package_data=True,
)
