#----------------------------------------------------------------------------------------
# From the managarm project
#----------------------------------------------------------------------------------------
FROM debian:sid AS base

RUN apt update \
	&& apt -y install \
		--no-install-recommends \
		autogen \
		autopoint \
		bc \
		bison \
		build-essential \
		cmake \
		cpio \
		curl \
		flex \
		libfl2 \
		gawk \
		gengetopt \
		gettext \
		git \
		gperf \
		groff \
		help2man \
		hwdata \
		intltool \
		itstool \
		libbz2-dev \
		liblzma-dev \
		libzstd-dev \
		libcanberra-dev \
		udev \
		libcurl4-openssl-dev \
		libelf-dev \
		libexpat1-dev \
		libgdk-pixbuf2.0-bin \
		libgirepository1.0-dev \
		libglib2.0-dev-bin \
		libglib2.0-dev \
		libgtk-4-bin \
		libgl-dev \
		libgtk-4-bin \
		libgmp-dev \
		libmpc-dev \
		libmpfr-dev \
		libmount-dev \
		libssl-dev \
		libpng-dev \
		libudev-dev \
		libwayland-dev \
		libx11-xcb-dev \
		libxkbcommon-x11-dev \
		libxfixes-dev \
		libxml2-dev \
		libyaml-dev \
        meson \
		m4 \
		mkbootimg \
		mtools \
		nasm \
		netpbm \
		ninja-build \
		p11-kit \
		patchelf \
		pkg-config \
		plasma-wayland-protocols \
		python3-gi \
		python3-jinja2 \
		python3-libxml2 \
		python3-mako \
		python3-pip \
		python3-setuptools \
		python3-wheel \
		python3-packaging \
		python3-xcbgen \
		rsync \
		ruby \
		sassc \
		texinfo \
		u-boot-tools \
		unifdef \
		unzip \
		wayland-protocols \
		wget \
		x11-apps \
		xcvt \
		xsltproc \
		zlib1g-dev \
		clangd \
		fdisk \
		dosfstools \
		mtools \
		libxcb-xinerama0-dev \
		libxcb-screensaver0-dev \
		libxcb-composite0-dev \
		libxcb-image0-dev \
		libxcb-record0-dev \
		libxcb-randr0-dev \
		libxcb-present-dev \
		libxcb-damage0-dev \
		libxcb-cursor-dev \
		libxcb-dri3-dev \
		libxcb-dri2-0-dev \
		libxcb-glx0-dev \
		libxcb-xinput-dev \
		libxcb-res0-dev \
		libxcb-xf86dri0-dev \
		libxcb-dpms0-dev \
		libxcb-ewmh-dev \
		libxcb-util0-dev \
		libxcb-keysyms1-dev \
		libxcb-icccm4-dev \
		&& apt clean

FROM base AS user
ARG USER=1000

RUN useradd -ms /bin/bash hbuild -u $USER
USER hbuild
WORKDIR /home/hbuild

RUN git config --global user.email "hbuild@localhost" \
	&& git config --global user.name "hbuild"

CMD ["bash"]
