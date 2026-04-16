# 音乐生成 (Music Generation) - MiniMax 开放平台文档中心

##### API 指引

*   [](https://platform.minimaxi.com/docs/api-reference/api-overview)
*   [](https://platform.minimaxi.com/docs/guides/rate-limits)
*   [](https://platform.minimaxi.com/docs/api-reference/errorcode)

![https://filecdn.minimax.chat/public/ebfd6f8e-5b5a-4edd-8253-6c731d3b368f.png](https://filecdn.minimax.chat/public/ebfd6f8e-5b5a-4edd-8253-6c731d3b368f.png)

##### 语音

*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/speech-t2a-http)
    *   [
        
        WSS
        
        ](https://platform.minimaxi.com/docs/api-reference/speech-t2a-websocket)
*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/speech-t2a-async-create)
    *   [
        
        GET
        
        ](https://platform.minimaxi.com/docs/api-reference/speech-t2a-async-query)
*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/voice-cloning-uploadcloneaudio)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/voice-cloning-uploadprompt)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/voice-cloning-clone)
*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/voice-design-design)
*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/voice-management-get)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/voice-management-delete)

![https://filecdn.minimax.chat/public/766ab356-4817-4bf1-8849-0f64728d811f.png](https://filecdn.minimax.chat/public/766ab356-4817-4bf1-8849-0f64728d811f.png)

##### 视频

*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/video-generation-t2v)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/video-generation-i2v)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/video-generation-fl2v)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/video-generation-s2v)
    *   [
        
        GET
        
        ](https://platform.minimaxi.com/docs/api-reference/video-generation-query)
    *   [
        
        GET
        
        ](https://platform.minimaxi.com/docs/api-reference/video-generation-download)

![https://filecdn.minimax.chat/public/c67ded66-6213-441f-b784-6866c6943aef.png](https://filecdn.minimax.chat/public/c67ded66-6213-441f-b784-6866c6943aef.png)

##### 图片

*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/image-generation-t2i)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/image-generation-i2i)

![https://filecdn.minimax.chat/public/0f1ab37b-78fd-41ab-945d-a20c1ac436b4.png](https://filecdn.minimax.chat/public/0f1ab37b-78fd-41ab-945d-a20c1ac436b4.png)

##### 音乐

*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/music-generation)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/lyrics-generation)

![https://filecdn.minimax.chat/public/1291e3fd-3307-4344-ba3e-40fa3780419f.png](https://filecdn.minimax.chat/public/1291e3fd-3307-4344-ba3e-40fa3780419f.png)

##### 文件

*   *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/file-management-upload)
    *   [
        
        GET
        
        ](https://platform.minimaxi.com/docs/api-reference/file-management-list)
    *   [
        
        GET
        
        ](https://platform.minimaxi.com/docs/api-reference/file-management-retrieve)
    *   [
        
        GET
        
        ](https://platform.minimaxi.com/docs/api-reference/file-management-retrieve-content)
    *   [
        
        POST
        
        ](https://platform.minimaxi.com/docs/api-reference/file-management-delete)

```
curl --request POST \
  --url https://api.minimaxi.com/v1/music_generation \
  --header 'Authorization: Bearer <token>' \
  --header 'Content-Type: application/json' \
  --data '
{
  "model": "music-2.6",
  "prompt": "独立民谣,忧郁,内省,渴望,独自漫步,咖啡馆",
  "lyrics": "[verse]\n街灯微亮晚风轻抚\n影子拉长独自漫步\n旧外套裹着深深忧郁\n不知去向渴望何处\n[chorus]\n推开木门香气弥漫\n熟悉的角落陌生人看",
  "audio_setting": {
    "sample_rate": 44100,
    "bitrate": 256000,
    "format": "mp3"
  }
}
'
```

```
{
  "data": {
    "audio": "hex编码的音频数据",
    "status": 2
  },
  "trace_id": "04ede0ab069fb1ba8be5156a24b1e081",
  "extra_info": {
    "music_duration": 25364,
    "music_sample_rate": 44100,
    "music_channel": 2,
    "bitrate": 256000,
    "music_size": 813651
  },
  "analysis_info": null,
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  }
}
```

使用本接口，输入歌词和歌曲描述，进行歌曲生成。

```
curl --request POST \
  --url https://api.minimaxi.com/v1/music_generation \
  --header 'Authorization: Bearer <token>' \
  --header 'Content-Type: application/json' \
  --data '
{
  "model": "music-2.6",
  "prompt": "独立民谣,忧郁,内省,渴望,独自漫步,咖啡馆",
  "lyrics": "[verse]\n街灯微亮晚风轻抚\n影子拉长独自漫步\n旧外套裹着深深忧郁\n不知去向渴望何处\n[chorus]\n推开木门香气弥漫\n熟悉的角落陌生人看",
  "audio_setting": {
    "sample_rate": 44100,
    "bitrate": 256000,
    "format": "mp3"
  }
}
'
```

```
{
  "data": {
    "audio": "hex编码的音频数据",
    "status": 2
  },
  "trace_id": "04ede0ab069fb1ba8be5156a24b1e081",
  "extra_info": {
    "music_duration": 25364,
    "music_sample_rate": 44100,
    "music_channel": 2,
    "bitrate": 256000,
    "music_size": 813651
  },
  "analysis_info": null,
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  }
}
```

#### 授权

`HTTP: Bearer Auth`

*   Security Scheme Type: http
*   HTTP Authorization Scheme: Bearer API\_key，用于验证账户信息，可在 [账户管理>接口密钥](https://platform.minimaxi.com/user-center/basic-information/interface-key) 中查看。

#### 请求头

Content-Type

enum<string>

默认值:application/json

必填

请求体的媒介类型，请设置为 `application/json`，确保请求数据的格式为 JSON

#### 请求体

使用的模型名称。可选值：

*   `music-2.6`（推荐）：文本生成音乐，仅限 Token Plan 用户和付费用户使用，RPM 较高
*   `music-cover`：基于参考音频生成翻唱版本，仅限 Token Plan 用户和付费用户使用，RPM 较高
*   `music-2.6-free`：`music-2.6` 的限免版本，所有用户可通过 API Key 使用，RPM 较低
*   `music-cover-free`：`music-cover` 的限免版本，所有用户可通过 API Key 使用，RPM 较低

可用选项

:

`music-2.6`,

`music-cover`,

`music-2.6-free`,

`music-cover-free`

音乐的描述，用于指定风格、情绪和场景。例如"流行音乐, 难过, 适合在下雨的晚上"。  
注意：

*   `music-2.6` / `music-2.6-free` 纯音乐（`is_instrumental: true`）：必填，长度限制 \[1, 2000\] 个字符
*   `music-2.6` / `music-2.6-free`（非纯音乐）：可选，长度限制 \[0, 2000\] 个字符
*   `music-cover` / `music-cover-free`：必填，描述目标翻唱风格，长度限制 \[10, 300\] 个字符

Maximum string length: `2000`

歌曲歌词，使用 `\n` 分隔每行。支持结构标签：`[Intro]`, `[Verse]`, `[Pre Chorus]`, `[Chorus]`, `[Interlude]`, `[Bridge]`, `[Outro]`, `[Post Chorus]`, `[Transition]`, `[Break]`, `[Hook]`, `[Build Up]`, `[Inst]`, `[Solo]`。  
注意：

*   `music-2.6` / `music-2.6-free` 纯音乐（`is_instrumental: true`）：非必填
*   `music-2.6` / `music-2.6-free`（非纯音乐）：必填，长度限制 \[1, 3500\] 个字符
*   `music-cover` / `music-cover-free`：可选，如不传则通过 ASR 自动从参考音频中提取歌词，长度限制 \[10, 1000\] 个字符
*   当 `lyrics_optimizer: true` 且 `lyrics` 为空时，系统将根据 `prompt` 自动生成歌词

Required string length: `1 - 3500`

音频的返回格式，可选值为 `url` 或 `hex`，默认为 `hex`。当 `stream` 为 `true` 时，仅支持 `hex` 格式。注意：url 的有效期为 24 小时，请及时下载

是否在音频末尾添加水印，默认为 `false`。仅在非流式 (`stream: false`) 请求时生效

是否根据 `prompt` 描述自动生成歌词。仅 `music-2.6` / `music-2.6-free` 支持。

设为 `true` 且 `lyrics` 为空时，系统会根据 prompt 自动生成歌词。默认为 `false`

是否生成纯音乐（无人声）。仅 `music-2.6` / `music-2.6-free` 支持。

设为 `true` 时，`lyrics` 字段非必填。默认为 `false`

参考音频的 URL 地址。仅用于 `music-cover` / `music-cover-free` 模型。`audio_url` 和 `audio_base64` 必须且只能提供其中一个。

参考音频要求：

*   时长：6 秒至 6 分钟
*   大小：最大 50 MB
*   格式：支持常见音频格式（mp3、wav、flac 等）

Base64 编码的参考音频。仅用于 `music-cover` / `music-cover-free` 模型。`audio_url` 和 `audio_base64` 必须且只能提供其中一个。

参考音频要求：

*   时长：6 秒至 6 分钟
*   大小：最大 50 MB
*   格式：支持常见音频格式（mp3、wav、flac 等）

#### 响应

[图生图](https://platform.minimaxi.com/docs/api-reference/image-generation-i2i)[歌词生成](https://platform.minimaxi.com/docs/api-reference/lyrics-generation)