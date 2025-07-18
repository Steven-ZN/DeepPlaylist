import csv
import time
import requests

#  Ollama 模型配置
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "deepseek-r1:14b"

# 输入输出文件
INPUT_CSV = "liked_songs.csv"
OUTPUT_CSV = "classified_songs.csv"

# 生成分类 prompt 的函数
def build_prompt(songname: str, singer: str, album: str = "") -> str:
    return f"""
你是一个音乐归类助手。请根据歌曲信息判断其语言和情绪标签。
语言选项：CN, JP, EN, Inst, Pure
情绪选项：Raise, Ease, Down, reflect, City_Pop
注意，reflect只有非常明显的反思：如time这种哲学意味的才归类；
City_Pop只有当歌手是日本的，而且演唱的是日本泡沫经济时代的音乐时候才归类。
请只返回 JSON 格式，字段为 \"language\" 和 \"emotion\"。

歌曲名：{songname}
歌手：{singer}
专辑：{album}
"""


import re
import json

def extract_json_from_text(text: str) -> dict:
    try:
        # 删除 <think> 标签块
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # 删除 markdown 包裹符
        text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()

        # 提取所有 JSON 块
        json_candidates = re.findall(r"{[^{}]*}", text, re.DOTALL)

        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)

                #  修复点：emotion 为 list 时只取第一个
                if "language" in parsed and "emotion" in parsed:
                    if isinstance(parsed["emotion"], list):
                        parsed["emotion"] = parsed["emotion"][0] if parsed["emotion"] else "Unknown"
                    return parsed

            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"JSON 提取失败: {e}")

    return {"language": "Unknown", "emotion": "Unknown"}





# 向 Ollama 请求模型推理
def classify_song_via_ollama(songname: str, singer: str, album: str = "") -> dict:
    prompt = build_prompt(songname, singer, album)
    try:
        response = requests.post(
            OLLAMA_API_URL,
            json={"model": MODEL_NAME, "prompt": prompt, "stream": False},
            timeout=60
        )
        result_text = response.json()["response"].strip()
        print(f"[{songname}] 模型回复: {result_text}")

        # 尝试用 eval 转成 dict
        result = extract_json_from_text(result_text)

        if isinstance(result, dict) and "language" in result and "emotion" in result:
            return result
    except Exception as e:
        print(f"出错: {e}")

    return {"language": "Unknown", "emotion": "Unknown"}

#主处理流程
def classify_all():
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        songs = list(reader)

    print(f"🎵 开始处理 {len(songs)} 首歌曲...")

    fieldnames = list(songs[0].keys()) + ["language", "emotion"]

    # 创建输出文件并写入 header（覆盖旧的）
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

    # 一首一首处理并写入
    for i, song in enumerate(songs, 1):
        name = song["歌名"]
        singer = song["歌手"]
        album = song.get("专辑", "")

        tag = classify_song_via_ollama(name, singer, album)
        song.update(tag)

        # 写入当前结果到 CSV
        with open(OUTPUT_CSV, "a", newline="", encoding="utf-8-sig") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writerow(song)

        print(f"[{i}/{len(songs)}] 已保存：{name}")
        time.sleep(1)  # 控制速率


if __name__ == "__main__":
    classify_all()
