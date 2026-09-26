import requests
import base64

def send_group_image(group_id, image_path, napcat_api, napcat_token):
    try:
        # 1. 读取图片并转成 Base64
        with open(image_path, "rb") as f:
            img_base64 = base64.b64encode(f.read()).decode('utf-8')
        
        # 2. 调用 NapCat 接口
        url = f"{napcat_api}/send_group_msg"
        headers = {"Authorization": f"Bearer {napcat_token}"}
        payload = {
            "group_id": group_id,
            "message": [{"type": "image", "data": {"file": f"base64://{img_base64}"}}]
        }
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        return response.json()
    except Exception as e:
        return {"status": "error", "msg": str(e)}