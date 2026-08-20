#!/usr/bin/env bash
# Put Lumi's saves back exactly as they were before overnight testing.
taskkill //F //IM Borderlands2.exe >/dev/null 2>&1; sleep 2
cp -r "D:/SteamLibrary/steamapps/common/Borderlands 2/BACKUP-saves-before-overnight-testing/." \
      "C:/Users/Lumi/Documents/My Games/Borderlands 2/WillowGame/SaveData/"
echo "saves restored"
