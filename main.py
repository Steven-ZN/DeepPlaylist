import asyncio
import time
import os
import platform
import json
import csv

from qqmusic_api.login import get_qrcode, check_qrcode, QRCodeLoginEvents, QRLoginType, check_expired
from qqmusic_api.user import get_fav_song, get_euin
from qqmusic_api.utils.credential import Credential

CREDENTIAL_PATH = "credential.json"

def save_credential(credential: Credential):
    with open(CREDENTIAL_PATH, "w", encoding="utf-8") as f:
        json.dump(credential.__dict__, f)

def load_credential() -> Credential | None:
    if not os.path.exists(CREDENTIAL_PATH):
        return None
    with open(CREDENTIAL_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
        c = Credential()
        c.__dict__.update(data)
        return c

async def login_or_restore():
    credential = load_credential()
    if credential:
        print("检测到本地登录信息，验证中...")
        if not await check_expired(credential):
            print("登录凭证有效，直接使用")
            return credential
        else:
            print("登录凭证已过期，将重新扫码")

    print("开始扫码登录")
    qr = await get_qrcode(QRLoginType.QQ)
    with open("login.png", "wb") as f:
        f.write(qr.data)

    if platform.system() == "Darwin":
        os.system("open login.png")
    elif platform.system() == "Windows":
        os.startfile("login.png")
    else:
        os.system("xdg-open login.png")

    while True:
        event, credential = await check_qrcode(qr)
        if event == QRCodeLoginEvents.DONE:
            print("登录成功！")
            save_credential(credential)
            return credential
        elif event in [QRCodeLoginEvents.REFUSE, QRCodeLoginEvents.TIMEOUT]:
            raise RuntimeError("扫码失败或过期")
        time.sleep(1)

async def main():
    credential = await login_or_restore()
    euin = await get_euin(credential.musicid)

    # 获取所有“我喜欢”歌曲
    first_page = await get_fav_song(euin=euin, page=1, num=50, credential=credential)
    total = first_page["total_song_num"]
    print(f"🎵 总共有 {total} 首“我喜欢”歌曲")
    all_songs = first_page["songlist"]
    page = 2
    while len(all_songs) < total:
        next_page = await get_fav_song(euin=euin, page=page, num=50, credential=credential)
        songs = next_page.get("songlist", [])
        if not songs:
            break
        all_songs.extend(songs)
        print(f"已获取 {len(all_songs)}/{total}")
        page += 1
        time.sleep(0.5)

    with open("liked_songs.csv", "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["歌名", "歌手", "专辑", "歌曲ID"])
        for song in all_songs:
            name = song.get("name", "")
            singer = song.get("singer", [{}])[0].get("name", "")
            album = song.get("album", {}).get("name", "")
            mid = song.get("mid", "")
            writer.writerow([name, singer, album, mid])

    print(f"已保存到 liked_songs.csv")

if __name__ == "__main__":
    asyncio.run(main())
