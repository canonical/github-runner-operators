.. meta::
   :description: Deploy and operate GARM and the GARM configurator with Juju.

.. vale Canonical.007-Headings-sentence-case = NO

.. _index:

GARM charms
===========

.. vale Canonical.007-Headings-sentence-case = YES

GARM (GitHub Actions Runner Manager) deploys and manages self-hosted GitHub
Actions runners. This project provides two Juju charms:

* the `garm` charm, which deploys and operates GARM;
* the `garm-configurator` charm, which configures runner scale sets for GARM.

Together, these charms let platform engineers and site reliability engineers
deploy GARM on Kubernetes, connect it to GitHub, and configure the runner
capacity required by their workflows.

In this documentation
---------------------

.. list-table::
    :header-rows: 1

    * -
      -
    * - Get started
      - :doc:`Deploy GARM and configure a runner scale set <tutorial/garm>`
    * - Operations
      - :doc:`Retrieve GARM administrator credentials <how-to/retrieve-garm-credentials>`
    * - Reference
      - :doc:`Architecture overview <reference/architecture>` | :doc:`Charm reference <reference/charms>`
    * - Releases
      - `Changelog <https://github.com/canonical/github-runner-operators/blob/main/docs/changelog.md>`_ | :doc:`Charm release and promotion process <explanation/charm-release-and-promotion>`

How this documentation is organized
------------------------------------

This documentation uses the `Diátaxis documentation structure <https://diataxis.fr/>`_.

- The :doc:`tutorial <tutorial/garm>` takes you step-by-step through deploying GARM and configuring a runner scale set.
- The :doc:`Retrieve GARM administrator credentials <how-to/retrieve-garm-credentials>` how-to guide covers a focused operational task.
- The :doc:`explanation <explanation/charm-release-and-promotion>` section includes background and context about the GARM charm release process.

Contributing to this documentation
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Documentation is an important part of the GARM charms project. We welcome
community contributions, suggestions, fixes, and constructive feedback on the
GARM and `garm-configurator` documentation.
See the :doc:`How to contribute <how-to/contribute>` guide for more information.

If you find a missing or incorrect topic, `open an issue on GitHub <https://github.com/canonical/github-runner-operators/issues>`_.


Project and community
---------------------

GARM and `garm-configurator` are open-source Juju charms maintained in the
`github-runner-operators repository <https://github.com/canonical/github-runner-operators>`_.
The project welcomes community contributions, suggestions, fixes, and
constructive feedback.

Governance and policies
^^^^^^^^^^^^^^^^^^^^^^^

- `Code of conduct <https://ubuntu.com/community/code-of-conduct>`_

Get involved
^^^^^^^^^^^^

- `Report an issue <https://github.com/canonical/github-runner-operators/issues>`_
- `Get support <https://discourse.charmhub.io/>`_
- `Join our online chat <https://matrix.to/#/#charmhub-charmdev:ubuntu.com>`_
- :doc:`Contribute <how-to/contribute>`

Releases
^^^^^^^^

- `Changelog <https://github.com/canonical/github-runner-operators/blob/main/docs/changelog.md>`_
- :doc:`Charm release and promotion process <explanation/charm-release-and-promotion>`

For questions, suggestions, or support, use the project issue tracker or one
of the community channels listed above.


.. vale Canonical.013-Spell-out-numbers-below-10 = NO
.. vale Canonical.500-Repeated-words = NO

.. toctree::
    :hidden:
    :maxdepth: 1

    Tutorial <tutorial/index>
    How-to guides <how-to/index>
    Reference <reference/index>
    Contribute <how-to/contribute>
    Explanation <explanation/index>
