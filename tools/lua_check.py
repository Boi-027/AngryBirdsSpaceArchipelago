"""Rough Lua 5.1 sanity check (no Lua interpreter on this machine): block and bracket balance.

usage: lua_check.py file.lua
"""
import re, sys

t = open(sys.argv[1], encoding="utf-8").read()
t = re.sub(r'"(\\.|[^"\\\n])*"', '""', t)          # strings first (they may contain '--')
t = re.sub(r"'(\\.|[^'\\\n])*'", "''", t)
t = re.sub(r"--[^\n]*", "", t)
words = re.findall(r"\b(function|if|for|while|repeat|end|until|do)\b", t)
opens = sum(w in ("function", "if", "repeat") for w in words) + sum(w in ("for", "while") for w in words)
closes = sum(w in ("end", "until") for w in words)
bal = {p: t.count(p[0]) - t.count(p[1]) for p in ("()", "{}", "[]")}
print(f"blocks open={opens} close={closes}  brackets {bal}")
sys.exit(0 if opens == closes and not any(bal.values()) else 1)
