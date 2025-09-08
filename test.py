import requests

def get_user_about_me(username):
    # Fetch user ID from username
    user_info_url = f"https://users.roblox.com/v1/usernames/users"
    response = requests.post(user_info_url, json={"usernames": [username]})
    if response.status_code == 200:
        user_data = response.json()
        if user_data["data"]:
            user_id = user_data["data"][0]["id"]
            
            # Fetch "About Me" using user ID
            about_me_url = f"https://users.roblox.com/v1/users/{user_id}"
            about_response = requests.get(about_me_url)
            if about_response.status_code == 200:
                about_data = about_response.json()
                return about_data.get("description", "No 'About Me' found.")
    return "User not found or an error occurred."

# Example usage
username = "VisHours"
print(get_user_about_me(username))