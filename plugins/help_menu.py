# plugins/help_menu.py

def get_help_menu(current_level):
    """根据当前权限等级，返回对应的可用指令菜单"""
    
    menu = "📋 **小橘3号 指令菜单**\n\n"
    
    # 1. 所有人可见的基础指令
    menu += "**【基础指令】**\n"
    menu += "· `/help` 或 `菜单`：查看此菜单\n"
    menu += "· `/register [名字]`：注册成为普通用户（Lv.2）\n"
    menu += "· `/cancel`：取消当前正在进行的操作\n\n"
    
    # 2. Lv.2 可见
    if current_level in ["Lv.2", "Lv.3", "Lv.4"]:
        menu += "**【普通用户指令】**\n"
        menu += "· `帮我读一下 [文件路径]`：读取沙箱内文件\n\n"
    
    # 3. Lv.3 可见
    if current_level in ["Lv.3", "Lv.4"]:
        menu += "**【代码编写者指令】**\n"
        menu += "· `/coder_auth [认证码]`：升级为代码编写者（Lv.3）\n"
        menu += "· `帮我写一个文件，路径 [路径]，内容 [内容]`：写入文件\n"
        menu += "· `/send_image [图片路径]`：发送本地图片到群里\n\n"
    
    # 4. Lv.4 可见
    if current_level == "Lv.4":
        menu += "**【最高权限（XUN）指令】**\n"
        menu += "· `/auth_xun [6位动态密码]`：在QQ/网页激活最高权限\n"
        menu += "· `xiaoju3_auth [6位动态密码]`：在香橙派本地终端激活最高权限\n"
        menu += "· `xiaoju3_stop`：在香橙派本地终端彻底停止机器人\n\n"
    
    menu += "---\n"
    menu += f"你当前的权限等级：**{current_level}**\n"
    menu += "如需升级权限，请使用上面对应的指令。"
    
    return menu