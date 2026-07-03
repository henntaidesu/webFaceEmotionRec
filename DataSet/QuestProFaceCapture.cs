// QuestProFaceCapture.cs
// Meta Quest Pro 面部表情采集 —— 读取 Face Tracking 的 63 维 blendshape，
// 写出与 DataSet/quest_pro_capture_spec.md 一致的 JSON，供 notebook 的 build_manifest() 读取。
//
// 依赖：Meta XR Core SDK / Movement SDK（提供 OVRFaceExpressions）。
// 场景前置：
//   1) OVRManager 上启用 Face Tracking（及所需权限），AndroidManifest 申请 FACE_TRACKING 权限。
//   2) 场景中放一个带 OVRFaceExpressions 组件的物体，拖到本脚本的 faceExpressions 字段。
//
// 注意：头显看不到自己的脸，图像需由【外接相机】拍 224×224 下半脸，按同一 sampleId 命名同步：
//   <sampleId>_central.jpg / <sampleId>_side.jpg
// 本脚本只负责 FEA + 元数据 JSON；图像采集在 Unity 外部完成（或另接 webcam 管线）。

using System;
using System.Collections;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

public class QuestProFaceCapture : MonoBehaviour
{
    [Header("引用")]
    [Tooltip("拖入带 OVRFaceExpressions 组件的物体")]
    public OVRFaceExpressions faceExpressions;

    [Header("采集设置")]
    [Tooltip("train / val / test")]
    public string split = "train";

    [Tooltip("受试者编号，用于拼 sampleId 与按身份划分数据集")]
    public string participantId = "p00";

    [Tooltip("当前提示的目标情感（EmoHeVRDB 名或本项目 key）")]
    public string currentLabel = "neutral";

    [Header("实时推送（驱动网页「微情感生成」）")]
    [Tooltip("开启后每帧把 63 维 FEA POST 到后端 /api/fea")]
    public bool enableLiveStream = true;

    [Tooltip("后端地址：PC 与头显同一局域网时填 PC 的 IP:9501。" +
             "用 Quest Link 在编辑器里跑则用 http://127.0.0.1:9501/api/fea")]
    public string backendUrl = "http://10.0.10.10:9501/api/fea";

    [Tooltip("推送频率（帧/秒），10~15 足够")]
    public float streamFps = 12f;

    private int _counter = 0;
    private string[] _blendshapeNames;
    private string _outRoot;

    // 与 OVRFaceExpressions.FaceExpression 枚举顺序一致的 63 维数据载体
    [Serializable]
    private class FaceSample
    {
        public string sample_id;
        public string label;
        public string image_central;
        public string image_side;
        public float[] blendshapes;
        public string[] blendshape_names;
        public string device = "Meta Quest Pro";
        public string sdk = "Meta XR Movement SDK - Face Tracking";
        public long timestamp_ms;
    }

    // 实时推送用的最小载体：JsonUtility 序列化为 {"blendshapes":[63],"timestamp_ms":..}
    [Serializable]
    private class FeaFrame
    {
        public float[] blendshapes;
        public long timestamp_ms;
    }

    private void Start()
    {
        if (faceExpressions == null)
            faceExpressions = FindObjectOfType<OVRFaceExpressions>();

        // 直接从枚举生成名字数组，保证顺序与本机 SDK 的实际枚举完全一致
        int n = (int)OVRFaceExpressions.FaceExpression.Max; // 63
        _blendshapeNames = new string[n];
        for (int i = 0; i < n; i++)
            _blendshapeNames[i] = ((OVRFaceExpressions.FaceExpression)i).ToString();

        _outRoot = Path.Combine(Application.persistentDataPath, "capture");
        Debug.Log($"[Capture] 输出根目录: {_outRoot}（blendshape 维度={n}）");

        if (enableLiveStream)
        {
            if (string.IsNullOrEmpty(backendUrl))
                Debug.LogWarning("[Stream] backendUrl 为空，实时推送未启动。");
            else
                StartCoroutine(StreamLoop());
        }
    }

    /// <summary>读取当前 63 维 blendshape（0~1）；数据无效返回 null。</summary>
    private float[] ReadWeights()
    {
        if (faceExpressions == null || !faceExpressions.ValidExpressions)
            return null;
        int n = (int)OVRFaceExpressions.FaceExpression.Max;
        var weights = new float[n];
        for (int i = 0; i < n; i++)
            weights[i] = faceExpressions[(OVRFaceExpressions.FaceExpression)i];
        return weights;
    }

    /// <summary>按 streamFps 频率把 FEA 推送到后端 /api/fea，驱动网页实时生成。</summary>
    private IEnumerator StreamLoop()
    {
        var wait = new WaitForSeconds(1f / Mathf.Max(1f, streamFps));
        Debug.Log($"[Stream] 开始实时推送 → {backendUrl}");
        while (true)
        {
            var weights = ReadWeights();
            if (weights != null)
            {
                var frame = new FeaFrame { blendshapes = weights, timestamp_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() };
                byte[] body = Encoding.UTF8.GetBytes(JsonUtility.ToJson(frame));
                using (var req = new UnityWebRequest(backendUrl, "POST"))
                {
                    req.uploadHandler = new UploadHandlerRaw(body);
                    req.downloadHandler = new DownloadHandlerBuffer();
                    req.SetRequestHeader("Content-Type", "application/json");
                    req.timeout = 3;
                    yield return req.SendWebRequest();
                    // 失败不打断循环（网络抖动/后端未起时静默重试）
                }
            }
            yield return wait;
        }
    }

    private void Update()
    {
        // 示例：按 A 键采集一帧（实际可由 UI 按钮 / 受试者控制器触发）
        if (OVRInput.GetDown(OVRInput.Button.One))
            CaptureSample(currentLabel);
    }

    /// <summary>采集当前帧的 63 维 blendshape 并写 JSON。返回 sampleId。</summary>
    public string CaptureSample(string label)
    {
        if (faceExpressions == null || !faceExpressions.ValidExpressions)
        {
            Debug.LogWarning("[Capture] 面部表情数据无效（未戴稳/未授权/未启用 Face Tracking），已跳过。");
            return null;
        }

        int n = (int)OVRFaceExpressions.FaceExpression.Max;
        var weights = new float[n];
        for (int i = 0; i < n; i++)
            weights[i] = faceExpressions[(OVRFaceExpressions.FaceExpression)i]; // 0~1

        string sampleId = $"{participantId}_e{_counter:D4}";
        _counter++;

        var sample = new FaceSample
        {
            sample_id = sampleId,
            label = label,
            image_central = sampleId + "_central.jpg",
            image_side = sampleId + "_side.jpg",
            blendshapes = weights,
            blendshape_names = _blendshapeNames,
            timestamp_ms = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
        };

        string dir = Path.Combine(_outRoot, split);
        Directory.CreateDirectory(dir);
        string path = Path.Combine(dir, sampleId + ".json");
        File.WriteAllText(path, JsonUtility.ToJson(sample, prettyPrint: true));

        Debug.Log($"[Capture] 写出 {path}  label={label}");
        // TODO：在此触发外接相机拍 224×224 图，命名为 image_central / image_side，存到同一 dir。
        return sampleId;
    }
}
