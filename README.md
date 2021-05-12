# SDP Helm Deployer

Helm deployment controller.

## Contribute to this repository

We use [Black](https://github.com/psf/black) to keep the python code style in good shape. 
Please make sure you black-formatted your code before merging to master.

The linting step in the CI pipeline checks that the code complies with black formatting style,
and fails if that is not the case.

## Releasing the Docker Image

When new release is ready:

  - check out master
  - update CHANGELOG.md
  - commit changes
  - make release-[patch||minor||major]

Note: bumpver needs to be installed