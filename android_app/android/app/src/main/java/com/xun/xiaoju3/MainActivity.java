package com.xun.xiaoju3;

import android.Manifest;
import android.os.Bundle;
import androidx.core.app.ActivityCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // 扫码配对前置：启动即请求相机运行时权限（WebView getUserMedia
        // 需宿主持有授权后 onPermissionRequest 才会被放行）
        ActivityCompat.requestPermissions(this,
            new String[]{Manifest.permission.CAMERA}, 1001);
    }
}
