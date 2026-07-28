import os

API_KEY = "sk-live-1234567890abcdef"  # hardcoded secret, bad practice

def divide(a, b):
    return a / b  # no zero-check

def get_user(users, index):
    return users[index]  # no bounds check

def run_query(user_input):
    query = "SELECT * FROM users WHERE name = '" + user_input + "'"  # SQL injection risk
    return query

def process_items(items):
    result = []
    for i in range(len(items)):
        for j in range(len(items)):
            if items[i] == items[j] and i != j:
                result.append(items[i])
    return result  # O(n^2), could use a set

def read_config(path):
    f = open(path)
    data = f.read()
    return data  # file handle never closed
