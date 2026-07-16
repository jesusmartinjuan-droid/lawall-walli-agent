#!/usr/bin/env bash
# Bootstrap de seguridad + Docker para el VPS de Walli.
# Ejecutar UNA VEZ, como root, justo después de crear el servidor:
#   scp infra/setup-server.sh root@<IP-del-VPS>:/root/
#   ssh root@<IP-del-VPS> "bash /root/setup-server.sh"
#
# A partir de aquí, usa el usuario `deploy` (no root) para todo lo demás,
# incluido el secret VPS_USER de GitHub Actions.
set -euo pipefail

DEPLOY_USER="deploy"

echo "==> Actualizando paquetes"
apt-get update -y
apt-get upgrade -y

echo "==> Instalando Docker"
curl -fsSL https://get.docker.com | sh

echo "==> Instalando ufw, fail2ban y unattended-upgrades"
apt-get install -y ufw fail2ban unattended-upgrades

echo "==> Creando usuario '${DEPLOY_USER}' sin privilegios de root por defecto"
if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
    adduser --disabled-password --gecos "" "${DEPLOY_USER}"
    usermod -aG sudo "${DEPLOY_USER}"
    usermod -aG docker "${DEPLOY_USER}"
    mkdir -p "/home/${DEPLOY_USER}/.ssh"
    cp /root/.ssh/authorized_keys "/home/${DEPLOY_USER}/.ssh/authorized_keys"
    chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "/home/${DEPLOY_USER}/.ssh"
    chmod 700 "/home/${DEPLOY_USER}/.ssh"
    chmod 600 "/home/${DEPLOY_USER}/.ssh/authorized_keys"
fi

echo "==> Carpeta de despliegue /opt/walli"
mkdir -p /opt/walli
chown "${DEPLOY_USER}:${DEPLOY_USER}" /opt/walli

echo "==> Firewall (ufw): solo SSH, HTTP y HTTPS"
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "==> fail2ban: protección contra fuerza bruta en SSH"
systemctl enable --now fail2ban

echo "==> unattended-upgrades: parches de seguridad automáticos"
dpkg-reconfigure -f noninteractive unattended-upgrades

echo "==> Endureciendo SSH: sin login de root, sin contraseña"
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh

echo ""
echo "==> Listo. A partir de ahora conéctate con:"
echo "      ssh ${DEPLOY_USER}@<IP-del-VPS>"
echo "    (el acceso como root por SSH ya está deshabilitado)"
