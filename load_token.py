#!/usr/bin/env python3
"""
读取txt文件，解析每行数据，执行API请求
数据格式: 用户名---密码---token
"""

import json
import sys
from typing import List

import requests


def parse_line(line: str) -> str:
    """
    解析单行数据，提取第三个值（token）
    格式: username---password---token
    """
    line = line.strip()
    if not line:
        return None

    parts = line.split("---")
    if len(parts) < 3:
        print(f"警告: 行格式错误，跳过: {line}")
        return None

    return parts[2].strip()


def process_file(filename: str) -> List[str]:
    """
    读取文件并解析所有token
    """
    tokens = []

    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f, 1):
                token = parse_line(line)
                if token:
                    tokens.append(token)
                    print(f"第{i}行: 提取到token (前20字符): {token[:20]}...")
                else:
                    print(f"第{i}行: 跳过")

    except FileNotFoundError:
        print(f"错误: 文件 '{filename}' 不存在")
        return []
    except Exception as e:
        print(f"错误: 读取文件失败 - {e}")
        return []

    print(f"\n成功提取到 {len(tokens)} 个token")
    return tokens


def send_request(tokens: List[str], url: str) -> dict:
    """
    发送API请求
    """
    if not tokens:
        print("错误: 没有有效的token可发送")
        return None

    # 构建请求数据
    payload = json.dumps({
        "pool": "super",
        "tokens": tokens
    })

    # 构建请求头
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer grok2api'
    }

    try:
        print(f"发送请求到: {url}")
        print(f"请求体: {payload[:100]}...")  # 只显示前100字符

        response = requests.request("POST", url, headers=headers, data=payload, timeout=30)

        print(f"\n响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")

        # 尝试解析JSON响应
        try:
            return response.json()
        except:
            return {"text": response.text, "status_code": response.status_code}

    except requests.exceptions.ConnectionError:
        print(f"错误: 无法连接到服务器 {url}")
        return None
    except requests.exceptions.Timeout:
        print("错误: 请求超时")
        return None
    except requests.exceptions.RequestException as e:
        print(f"错误: 请求失败 - {e}")
        return None


def main():
    """
    主函数
    """
    # 配置参数
    # 修改这里的URL为你需要的地址
    API_URL = "http://64.32.31.178:8427/admin/api/tokens/add"

    filename=r'C:\Users\xufus\xwechat_files\wxid_hwvqgzdm9acp41_9198\msg\file\2026-04\subscribed_2026-04-18.txt'
    print(f"处理文件: {filename}")
    print(f"API地址: {API_URL}")
    print("=" * 50)

    # 处理文件
    tokens = process_file(filename)

    if not tokens:
        print("没有找到有效的token，程序退出")
        return

    # 询问用户确认
    print("\n" + "=" * 50)
    print(f"准备发送 {len(tokens)} 个token到API")
    confirm = input("确认发送? (y/N): ").strip().lower()

    if confirm != 'y':
        print("操作已取消")
        return

    # 发送请求
    print("\n发送请求中...")
    result = send_request(tokens, API_URL)

    if result:
        print("\n请求完成!")
    else:
        print("\n请求失败!")


if __name__ == "__main__":
    main()
