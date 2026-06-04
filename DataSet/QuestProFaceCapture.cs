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
using System.IO;
using UnityEngine;

[RequireComponent(typeof(Camera))] // 仅为方便挂载；如不需要可删
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
