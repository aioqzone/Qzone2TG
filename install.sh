# apt or yum
if type apt; then useapt=true
elif type yum; then useyum=true
else return 1
fi
# install python and git
if ${useapt}; then 
apt update && apt upgrade
apt install -y python3 python3-pip git
elif ${useyum}; then
yum update && yum upgrade
yum install -y python3 python3-pip git
fi
# install dependency
pip3 install python-telegram-bot python-telegram-bot[socks] selenium demjson lxml PIL
# clone source code
git clone https://github.com/JamzumSum/Qzone2TG.git
cd Qzone2TG
# read file
conf=$(cat example.json)
# get qq
read -p "Enter your QQ number: " QQ
read -p "Enter your bot token: " token
#save config
echo $(printf "${conf}" ${QQ} ${token}) > config.json
echo "configuration done."
echo "if you'd like use a proxy, see https://github.com/JamzumSum/Qzone2TG#%E7%AE%80%E5%8D%95%E5%BC%80%E5%A7%8B"