# Base OS
FROM ghcr.io/biosimulators/biosimulators_pysces/pysces_base:latest

ARG VERSION=0.1.25
ARG SIMULATOR_VERSION="1.2.2"

# metadata
LABEL \
    org.opencontainers.image.title="PySCeS" \
    org.opencontainers.image.version="${SIMULATOR_VERSION}" \
    org.opencontainers.image.description="Simulation and analysis tools for modelling biological systems" \
    org.opencontainers.image.url="https://pysces.github.io/" \
    org.opencontainers.image.documentation="https://pyscesdocs.readthedocs.io/" \
    org.opencontainers.image.source="https://github.com/biosimulators/Biosimulators_PySCeS" \
    org.opencontainers.image.authors="BioSimulators Team <info@biosimulators.org>" \
    org.opencontainers.image.vendor="BioSimulators Team" \
    org.opencontainers.image.licenses="BSD-3-Clause" \
    \
    base_image="python:3.10-slim-bookworm" \
    version="${VERSION}" \
    software="PySCeS" \
    software.version="${SIMULATOR_VERSION}" \
    about.summary="Simulation and analysis tools for modelling biological systems" \
    about.home="https://pysces.github.io/" \
    about.documentation="https://pyscesdocs.readthedocs.io/" \
    about.license_file="https://github.com/PySCeS/pysces/blob/master/LICENSE" \
    about.license="SPDX:BSD-3-Clause" \
    about.tags="BioSimulators,mathematical model,kinetic model,simulation,systems biology,computational biology,SBML,SED-ML,COMBINE,OMEX" \
    extra.identifiers.biotools="pysces" \
    maintainer="BioSimulators Team <info@biosimulators.org>"

# install PySCeS
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends \
        libgfortran5 \
    \
    && pip install "pysces[parscan,sbml]==${SIMULATOR_VERSION}" \
    \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists

# Copy code for command-line interface into image and install it
COPY . /root/Biosimulators_PySCeS
RUN pip install /root/Biosimulators_PySCeS \
    && mkdir -p /Pysces \
    && mkdir -p /Pysces/psc \
    && mkdir -p /root/Pysces \
    && mkdir -p /root/Pysces/psc \
    && chmod ugo+rw -R /Pysces \
    && cp /root/Biosimulators_PySCeS/.pys_usercfg.Dockerfile.ini /Pysces/.pys_usercfg.ini \
    && cp /root/Biosimulators_PySCeS/.pys_usercfg.Dockerfile.ini /root/Pysces/.pys_usercfg.ini \
    && rm -rf /root/Biosimulators_PySCeS

# supported environment variables
ENV ALGORITHM_SUBSTITUTION_POLICY=SIMILAR_VARIABLES \
    VERBOSE=0 \
    MPLBACKEND=PDF

# Entrypoint
ENTRYPOINT ["biosimulators-pysces"]
CMD []
