# S3 多桶目录映射

在“系统设置 → 映射 → S3 映射”中配置 Access Key、Secret Key 和桶目录映射。每个桶包含唯一的桶名与基础路径；基础路径是 Foxel 虚拟文件系统中的目录，可以手动填写或通过目录选择器选择。

例如：

| 桶名 | 基础路径 | 对象 `photo.jpg` 对应的文件 |
| --- | --- | --- |
| `photos` | `/local/photos` | `/local/photos/photo.jpg` |
| `backups` | `/remote/backups` | `/remote/backups/photo.jpg` |

所有桶共用 S3 访问地址 `/s3`、Access Key、Secret Key 和 Region。配置保存后立即生效。目录映射不创建新的存储适配器，请先在 Foxel 中配置相应的挂载目录。不同桶的目录如果重叠，可能访问到同一文件。

## 配置兼容

新增配置项 `S3_MAPPING_BUCKETS`，值为 JSON 字符串，也可以通过同名环境变量提供：

```json
[
  {"name": "photos", "base_path": "/local/photos"},
  {"name": "backups", "base_path": "/remote/backups"}
]
```

未配置或值为空时，继续使用原有 `S3_MAPPING_BUCKET` 与 `S3_MAPPING_BASE_PATH`。设置页面会把旧配置显示为一条映射，首次保存后使用新的列表配置。非空列表配置优先于旧配置，格式错误时接口返回错误，不会回退暴露旧目录。

桶名须为 1-63 位字母、数字、点、下划线或连字符，并以字母或数字开头；使用常规小写 S3 桶名可提高客户端兼容性。目录和对象路径禁止包含反斜杠、控制字符与 `.` / `..` 路径段。

分片上传绑定创建时的桶名、对象名和目标目录。桶改名、删除或修改基础路径后，旧上传不能在新映射下继续或合并，需要重新发起上传。移除桶只移除映射，不删除目录中的文件。

## 手动验证

使用已配置的 Access Key 和 Secret Key 为 AWS CLI 配置凭据，访问方式为 path-style：

```bash
aws --endpoint-url http://localhost:8000/s3 s3 ls
aws --endpoint-url http://localhost:8000/s3 s3 ls s3://photos/
aws --endpoint-url http://localhost:8000/s3 s3 cp ./photo.jpg s3://photos/photo.jpg
aws --endpoint-url http://localhost:8000/s3 s3 cp s3://photos/photo.jpg ./downloaded.jpg
aws --endpoint-url http://localhost:8000/s3 s3 rm s3://photos/photo.jpg
```

建议分别验证两个桶中的同名文件是否落在各自目录，保存后刷新设置是否保留映射，以及移除桶后访问是否返回 `NoSuchBucket`。大文件上传还可验证分片上传和下载内容是否一致。
