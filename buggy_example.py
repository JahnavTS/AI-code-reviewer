import os

API_KEY = "sk-live-1234567890abcdef"  

def divide(a, b):
    return a / b  

def get_user(users, index):
    return users[index]  

def run_query(user_input):
    query = "SELECT * FROM users WHERE name = '" + user_input + "'"  
    return query

def process_items(items):
    result = []
    for i in range(len(items)):
        for j in range(len(items)):
            if items[i] == items[j] and i != j:
                result.append(items[i])
    return result  

def read_config(path):
    f = open(path)
    data = f.read()
    return data  
