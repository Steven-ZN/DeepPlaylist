import csv
import time
import requests
import re
import json

# Ollama 模型配置
OLLAMA_API_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "deepseek-r1:14b"

# 输入输出文件
INPUT_CSV = "classified_songs.csv"
OUTPUT_CSV = "classified_songs_completed.csv"

def build_prompt(songname: str, singer: str, album: str = "") -> str:
    return f"""
你是一个音乐归类助手。请根据歌曲信息判断其语言和情绪标签。
语言选项：CN, JP, EN, Inst, Pure
情绪选项：Raise, Ease, Down, reflect, City_Pop
注意，reflect只有非常明显的反思：如time这种哲学意味的才归类；
City_Pop只有当歌手是日本的，而且演唱的是日本泡沫经济时代的音乐时候才归类。
请只返回 JSON 格式，字段为 "language" 和 "emotion"，且 emotion 只返回一个最相关标签，不要是数组。

歌曲名：{songname}
歌手：{singer}
专辑：{album}
"""

def extract_json_from_text(text: str) -> dict:
    try:
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"```json|```", "", text, flags=re.IGNORECASE).strip()
        json_candidates = re.findall(r"{[^{}]*}", text, re.DOTALL)
        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate)
                if "language" in parsed and "emotion" in parsed:
                    if isinstance(parsed["emotion"], list):
                        parsed["emotion"] = parsed["emotion"][0] if parsed["emotion"] else "Unknown"
                    return parsed
            except json.JSONDecodeError:
                continue
    except Exception as e:
        print(f"JSON 提取失败: {e}")
    return {"language": "Unknown", "emotion": "Unknown"}

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
        return extract_json_from_text(result_text)
    except Exception as e:
        print(f"出错: {e}")
    return {"language": "Unknown", "emotion": "Unknown"}

def needs_fix(value: str) -> bool:
    if value is None:
        return True
    value = str(value).strip().lower()
    return value in ["", "unknown", "[]", "null"]

def fix_all():
    with open(INPUT_CSV, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        songs = list(reader)

    print(f"检查并补全 {len(songs)} 首歌曲...")

    fieldnames = list(songs[0].keys())

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f_out:
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for i, song in enumerate(songs, 1):
            lang_missing = "language" not in song or needs_fix(song["language"])
            emo_missing = "emotion" not in song or needs_fix(song["emotion"])

            if lang_missing or emo_missing:
                print(f"修复第 {i} 条: {song['歌名']}")
                fix = classify_song_via_ollama(song["歌名"], song["歌手"], song.get("专辑", ""))
                if lang_missing:
                    song["language"] = fix["language"]
                if emo_missing:
                    song["emotion"] = fix["emotion"]
                time.sleep(1)  # 控制速率

            writer.writerow(song)

        print(f"所有补全结果已写入 {OUTPUT_CSV}")

if __name__ == "__main__":
    fix_all()
