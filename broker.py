def get_smart_api_session():
    """
    गुगल फायरबेस डेटाबेसमधून युजरचे क्रेडेंशियल्स वाचून एंजेल वनला ऑटो-लॉगिन करतो.
    """
    global _smart_api_session, _last_error
    if _smart_api_session is not None:
        return _smart_api_session

    try:
        # main.py मधील फायरबेस 'db' ऑब्जेक्टचा वापर करणे
        from main import db
        if db is None:
            _last_error = "फायरबेस डेटाबेसशी कनेक्शन जोडलेले नाही!"
            return None
            
        # डेटाबेसमधून गुपित व्हॅल्यूज आणणे
        user_data = db.collection('users').document('user_01').get().to_dict()
        
        api_key = user_data.get("broker_api_key")
        client_code = user_data.get("broker_client_id")
        login_password = user_data.get("broker_mpin") # ४-अंकी एमपिन
        totp_secret = user_data.get("broker_totp_secret")

        if not all([api_key, client_code, login_password, totp_secret]):
            _last_error = "ॲपमध्ये अजून ब्रोकर सेटिंग्स अपूर्ण आहेत!"
            print(f"Angel One error: {_last_error}")
            return None

        from SmartApi import SmartConnect
        obj = SmartConnect(api_key=api_key)
        totp = pyotp.TOTP(totp_secret).now()
        
        session_data = obj.generateSession(client_code, login_password, totp)

        if not session_data.get("status"):
            _last_error = str(session_data)
            print(f"Angel One login fail: {_last_error}")
            return None

        _smart_api_session = obj
        print("✅ Angel One Dynamic MPIN session yashasvi zaale.")
        return obj
    except Exception as e:
        _last_error = str(e)
        print(f"Angel One session error: {_last_error}")
        return None
