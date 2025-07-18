import asyncio
import time
import os
import platform
import json
import pandas as pd

from qqmusic_api.login import (
    get_qrcode,
    check_qrcode,
    QRCodeLoginEvents,
    QRLoginType,
    check_expired,
)
from qqmusic_api.user import get_created_songlist
from qqmusic_api.songlist import add_songs, create
from qqmusic_api.song import query_song
from qqmusic_api.utils.credential import Credential

CSV_PATH = "classified_songs.csv"
CREDENTIAL_PATH = "credential.json"

# ------- 凭证缓存逻辑 -------
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


# ---------- songMid 批量转 songId ----------
async def mids_to_ids(mids: list[str]) -> list[int]:
    """把 14 位 songMid 列表转成纯数字 songId 列表"""
    ids: list[int] = []
    batch = 50  # QQ 接口一次最多 50 首
    for i in range(0, len(mids), batch):
        seg = mids[i : i + batch]
        tracks = await query_song(seg)  # 返回 list[dict]
        for t in tracks:
            sid = t.get("id")
            if isinstance(sid, int) and sid > 0:
                ids.append(sid)
            else:
                print(f"无法解析 songMid={t.get('mid')}")
        await asyncio.sleep(0.3)  # 防止限流
    return ids


async def login_or_restore() -> Credential:
    credential = load_credential()
    if credential:
        print("检测到本地登录信息，验证中...")
        try:
            if not await check_expired(credential):
                print("登录凭证有效，直接使用")
                return credential
            print("登录凭证已过期，将重新扫码")
        except Exception:
            print("检测凭证时出错，改为重新扫码")

    print("开始扫码登录")
    qr = await get_qrcode(QRLoginType.QQ)
    with open("login.png", "wb") as f:
        f.write(qr.data)
    if platform.system() == "Windows":
        os.startfile("login.png")
    elif platform.system() == "Darwin":
        os.system("open login.png")
    else:
        os.system("xdg-open login.png")

    while True:
        event, credential = await check_qrcode(qr)
        if event == QRCodeLoginEvents.DONE:
            print("登录成功！")
            save_credential(credential)
            return credential
        if event in (QRCodeLoginEvents.REFUSE, QRCodeLoginEvents.TIMEOUT):
            raise RuntimeError("扫码失败或过期")
        time.sleep(1)


# ---------- 主流程 ----------
async def main():
    credential = await login_or_restore()

    print("加载 CSV 文件...")
    df = pd.read_csv(CSV_PATH)
    df = df[["song_id", "language", "emotion"]].dropna()
    df["分类"] = df["language"].str.strip() + "_" + df["emotion"].str.strip()

    # 辅助函数：兼容不同字段
    def _get_name(d: dict):
        return d.get("diss_name") or d.get("dirName") or d.get("name")

    def _get_dirid(d: dict):
        return d.get("dirid") or d.get("dirId") or d.get("dir_id")

    print("获取账号歌单目录...")
    all_lists = await get_created_songlist(uin=str(credential.musicid))
    name_to_dirid = {
        _get_name(d): _get_dirid(d)
        for d in all_lists
        if _get_name(d) and _get_dirid(d) is not None
    }
    print("现有歌单：", list(name_to_dirid.keys()))

    for cat, group in df.groupby("分类"):
        # 若账号没有该歌单 -> 自动创建
        if cat not in name_to_dirid:
            print(f"歌单 [{cat}] 不存在，正在创建")
            created = await create(cat, credential=credential)
            name_to_dirid[cat] = _get_dirid(created)

        dirid = name_to_dirid[cat]
        mids = group["song_id"].astype(str).tolist()
        song_ids = await mids_to_ids(mids)
        if not song_ids:
            print(f"[{cat}] 无可上传的 songId，已跳过")
            continue

        print(f"🎵 正在向 [{cat}] 上传 {len(song_ids)} 首...")
        await add_songs(dirid=dirid, song_ids=song_ids, credential=credential)

    print("🏁 全部上传完成！")


if __name__ == "__main__":
    asyncio.run(main())
