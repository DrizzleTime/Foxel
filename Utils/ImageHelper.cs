using SixLabors.ImageSharp;
using SixLabors.ImageSharp.Processing;
using SixLabors.ImageSharp.Metadata.Profiles.Exif;
using System.Globalization;
using Foxel.Models;
using Foxel.Models.Enums;

namespace Foxel.Utils;

/// <summary>
/// 图片处理工具类
/// </summary>
public static class ImageHelper
{
    /// <summary>
    /// 创建缩略图
    /// </summary>
    /// <param name="originalPath">原始图片路径</param>
    /// <param name="thumbnailPath">缩略图保存路径</param>
    /// <param name="maxWidth">缩略图最大宽度</param>
    /// <param name="quality">压缩质量(1-100)</param>
    /// <returns>生成的缩略图的文件大小（字节）</returns>
    public static async Task<long> CreateThumbnailAsync(string originalPath, string thumbnailPath, int maxWidth,
        int quality = 75)
    {
        // 获取原始文件大小
        var originalFileInfo = new FileInfo(originalPath);
        long originalSize = originalFileInfo.Length;

        using var image = await Image.LoadAsync(originalPath);

        image.Metadata.ExifProfile = null;

        image.Mutate(x => x.Resize(new ResizeOptions
        {
            Size = new Size(maxWidth, 0),
            Mode = ResizeMode.Max
        }));

        string webpThumbnailPath = Path.ChangeExtension(thumbnailPath, ".webp");

        int adjustedQuality = AdjustQualityByFileSize(originalSize, ".webp", quality);

        await image.SaveAsWebpAsync(webpThumbnailPath, new SixLabors.ImageSharp.Formats.Webp.WebpEncoder
        {
            Quality = adjustedQuality,
            Method = SixLabors.ImageSharp.Formats.Webp.WebpEncodingMethod.BestQuality
        });

        var thumbnailFileInfo = new FileInfo(webpThumbnailPath);
        if (thumbnailFileInfo.Length < originalSize) return thumbnailFileInfo.Length;

        await image.SaveAsWebpAsync(webpThumbnailPath, new SixLabors.ImageSharp.Formats.Webp.WebpEncoder
        {
            Quality = Math.Max(adjustedQuality - 15, 50),
            Method = SixLabors.ImageSharp.Formats.Webp.WebpEncodingMethod.BestQuality
        });
        thumbnailFileInfo = new FileInfo(webpThumbnailPath);

        return thumbnailFileInfo.Length;
    }

    /// <summary>
    /// 根据原始文件大小调整质量参数
    /// </summary>
    private static int AdjustQualityByFileSize(long originalSize, string extension, int baseQuality)
    {
        if (extension == ".webp")
        {
            if (originalSize > 10 * 1024 * 1024) // 10MB
                return Math.Min(baseQuality, 70);
            else if (originalSize > 5 * 1024 * 1024) // 5MB
                return Math.Min(baseQuality, 75);
            else if (originalSize > 1 * 1024 * 1024) // 1MB
                return Math.Min(baseQuality, 80);
        }
        else if (extension == ".jpg" || extension == ".jpeg")
        {
            if (originalSize > 10 * 1024 * 1024) // 10MB
                return Math.Min(baseQuality, 65);
            else if (originalSize > 5 * 1024 * 1024) // 5MB
                return Math.Min(baseQuality, 70);
            else if (originalSize > 1 * 1024 * 1024) // 1MB
                return Math.Min(baseQuality, 75);
        }

        return baseQuality;
    }

    /// <summary>
    /// 将图片转换为Base64编码
    /// </summary>
    /// <param name="imagePath">图片路径</param>
    /// <returns>Base64编码字符串</returns>
    public static async Task<string> ConvertImageToBase64(string imagePath)
    {
        byte[] imageBytes = await File.ReadAllBytesAsync(imagePath);
        return Convert.ToBase64String(imageBytes);
    }

    /// <summary>
    /// 提取图片的EXIF信息
    /// </summary>
    /// <param name="imagePath">图片路径</param>
    /// <returns>EXIF信息对象</returns>
    public static async Task<ExifInfo> ExtractExifInfoAsync(string imagePath)
    {
        var exifInfo = new ExifInfo();

        try
        {
            // 确保文件存在
            if (!File.Exists(imagePath))
            {
                exifInfo.ErrorMessage = "找不到图片文件";
                return exifInfo;
            }

            // 使用ImageSharp读取EXIF信息
            using var image = await Image.LoadAsync(imagePath);
            var exifProfile = image.Metadata.ExifProfile;

            // 添加基本图像信息
            exifInfo.Width = image.Width;
            exifInfo.Height = image.Height;

            if (exifProfile != null)
            {
                // 提取相机信息
                if (exifProfile.TryGetValue(ExifTag.Make, out var make))
                    exifInfo.CameraMaker = make.Value;

                if (exifProfile.TryGetValue(ExifTag.Model, out var model))
                    exifInfo.CameraModel = model.Value;

                if (exifProfile.TryGetValue(ExifTag.Software, out var software))
                    exifInfo.Software = software.Value;

                // 提取拍摄参数
                if (exifProfile.TryGetValue(ExifTag.ExposureTime, out var exposureTime))
                    exifInfo.ExposureTime = exposureTime.Value.ToString();

                if (exifProfile.TryGetValue(ExifTag.FNumber, out var fNumber))
                    exifInfo.Aperture = $"f/{fNumber.Value}";

                if (exifProfile.TryGetValue(ExifTag.ISOSpeedRatings, out var iso))
                {
                    if (iso.Value is { Length: > 0 } isoArray)
                    {
                        exifInfo.IsoSpeed = isoArray[0].ToString();
                    }
                    else
                    {
                        exifInfo.IsoSpeed = iso.Value?.ToString();
                    }
                }

                if (exifProfile.TryGetValue(ExifTag.FocalLength, out var focalLength))
                    exifInfo.FocalLength = $"{focalLength.Value}mm";

                if (exifProfile.TryGetValue(ExifTag.Flash, out var flash))
                    exifInfo.Flash = flash.Value.ToString();

                if (exifProfile.TryGetValue(ExifTag.MeteringMode, out var meteringMode))
                    exifInfo.MeteringMode = meteringMode.Value.ToString();

                if (exifProfile.TryGetValue(ExifTag.WhiteBalance, out var whiteBalance))
                    exifInfo.WhiteBalance = whiteBalance.Value.ToString();

                // 提取时间信息并确保存储为字符串
                if (exifProfile.TryGetValue(ExifTag.DateTimeOriginal, out var dateTime))
                {
                    exifInfo.DateTimeOriginal = dateTime.Value;

                    // 解析日期时间
                    if (DateTime.TryParseExact(dateTime.Value, "yyyy:MM:dd HH:mm:ss", CultureInfo.InvariantCulture,
                            DateTimeStyles.None, out _))
                    {
                        // 只在ExifInfo中保留原始字符串格式
                    }
                }

                // 提取GPS信息
                if (exifProfile.TryGetValue(ExifTag.GPSLatitude, out var latitude) &&
                    exifProfile.TryGetValue(ExifTag.GPSLatitudeRef, out var latitudeRef))
                {
                    string? latRef = latitudeRef.Value;
                    exifInfo.GpsLatitude = ConvertGpsCoordinateToString(latitude.Value, latRef == "S");
                }

                if (exifProfile.TryGetValue(ExifTag.GPSLongitude, out var longitude) &&
                    exifProfile.TryGetValue(ExifTag.GPSLongitudeRef, out var longitudeRef))
                {
                    string? longRef = longitudeRef.Value;
                    exifInfo.GpsLongitude = ConvertGpsCoordinateToString(longitude.Value, longRef == "W");
                }
            }
        }
        catch (Exception ex)
        {
            exifInfo.ErrorMessage = $"提取EXIF信息时出错: {ex.Message}";
        }

        return exifInfo;
    }

    /// <summary>
    /// 将GPS坐标转换为字符串表示
    /// </summary>
    /// <param name="rationals">GPS坐标的有理数数组（度、分、秒）</param>
    /// <param name="isNegative">是否为负值（南纬/西经）</param>
    /// <returns>十进制格式的GPS坐标</returns>
    private static string? ConvertGpsCoordinateToString(Rational[]? rationals, bool isNegative)
    {
        if (rationals == null || rationals.Length < 3)
            return null;

        try
        {
            // 度分秒转换为十进制度
            double degrees = rationals[0].Numerator / (double)rationals[0].Denominator;
            double minutes = rationals[1].Numerator / (double)rationals[1].Denominator;
            double seconds = rationals[2].Numerator / (double)rationals[2].Denominator;

            double coordinate = degrees + (minutes / 60) + (seconds / 3600);

            // 如果是南纬或西经，则为负值
            if (isNegative)
                coordinate = -coordinate;

            return coordinate.ToString(CultureInfo.InvariantCulture);
        }
        catch
        {
            return null;
        }
    }

    /// <summary>
    /// 从EXIF信息中解析拍摄时间
    /// </summary>
    /// <param name="dateTimeOriginal">EXIF中的拍摄时间字符串</param>
    /// <returns>UTC格式的日期时间，如果解析失败则返回null</returns>
    public static DateTime? ParseExifDateTime(string? dateTimeOriginal)
    {
        if (string.IsNullOrEmpty(dateTimeOriginal))
            return null;

        if (DateTime.TryParseExact(dateTimeOriginal, "yyyy:MM:dd HH:mm:ss", CultureInfo.InvariantCulture,
                DateTimeStyles.None, out var parsedDate))
        {
            return DateTime.SpecifyKind(parsedDate, DateTimeKind.Local).ToUniversalTime();
        }

        return null;
    }

    /// <summary>
    /// 转换图片格式（无损转换并保留EXIF信息）
    /// </summary>
    /// <param name="inputPath">输入图片路径</param>
    /// <param name="outputPath">输出图片路径</param>
    /// <param name="targetFormat">目标格式</param>
    /// <param name="quality">压缩质量(仅对JPEG和WebP有效，1-100)</param>
    /// <returns>转换后的文件路径</returns>
    public static async Task<string> ConvertImageFormatAsync(string inputPath, string outputPath, ImageFormat targetFormat, int quality = 95)
    {
        if (targetFormat == ImageFormat.Original)
        {
            // 如果是原格式，直接返回输入路径
            return inputPath;
        }

        using var image = await Image.LoadAsync(inputPath);

        // 保留原始EXIF信息
        var originalExifProfile = image.Metadata.ExifProfile;

        // 根据目标格式确定文件扩展名和输出路径
        string extension = GetFileExtensionFromFormat(targetFormat);
        string finalOutputPath = Path.ChangeExtension(outputPath, extension);

        switch (targetFormat)
        {
            case ImageFormat.Jpeg:
                await image.SaveAsJpegAsync(finalOutputPath, new SixLabors.ImageSharp.Formats.Jpeg.JpegEncoder
                {
                    Quality = quality
                });
                break;

            case ImageFormat.Png:
                await image.SaveAsPngAsync(finalOutputPath, new SixLabors.ImageSharp.Formats.Png.PngEncoder
                {
                    CompressionLevel = SixLabors.ImageSharp.Formats.Png.PngCompressionLevel.BestCompression,
                    ColorType = SixLabors.ImageSharp.Formats.Png.PngColorType.RgbWithAlpha
                });
                break;

            case ImageFormat.WebP:
                await image.SaveAsWebpAsync(finalOutputPath, new SixLabors.ImageSharp.Formats.Webp.WebpEncoder
                {
                    Quality = quality,
                    Method = SixLabors.ImageSharp.Formats.Webp.WebpEncodingMethod.BestQuality
                });
                break;
            default:
                throw new NotSupportedException($"不支持的图片格式: {targetFormat}");
        }

        // 如果原图有EXIF信息，保存到转换后的图片中
        if (originalExifProfile != null)
        {
            using var convertedImage = await Image.LoadAsync(finalOutputPath);
            convertedImage.Metadata.ExifProfile = originalExifProfile;

            switch (targetFormat)
            {
                case ImageFormat.Jpeg:
                    await convertedImage.SaveAsJpegAsync(finalOutputPath, new SixLabors.ImageSharp.Formats.Jpeg.JpegEncoder
                    {
                        Quality = quality
                    });
                    break;

                case ImageFormat.Png:
                    await convertedImage.SaveAsPngAsync(finalOutputPath, new SixLabors.ImageSharp.Formats.Png.PngEncoder
                    {
                        CompressionLevel = SixLabors.ImageSharp.Formats.Png.PngCompressionLevel.BestCompression,
                        ColorType = SixLabors.ImageSharp.Formats.Png.PngColorType.RgbWithAlpha
                    });
                    break;

                case ImageFormat.WebP:
                    await convertedImage.SaveAsWebpAsync(finalOutputPath, new SixLabors.ImageSharp.Formats.Webp.WebpEncoder
                    {
                        Quality = quality,
                        Method = SixLabors.ImageSharp.Formats.Webp.WebpEncodingMethod.BestQuality
                    });
                    break;
            }
        }

        return finalOutputPath;
    }

    /// <summary>
    /// 根据图片格式获取文件扩展名
    /// </summary>
    /// <param name="format">图片格式</param>
    /// <returns>文件扩展名</returns>
    public static string GetFileExtensionFromFormat(ImageFormat format)
    {
        return format switch
        {
            ImageFormat.Jpeg => ".jpg",
            ImageFormat.Png => ".png",
            ImageFormat.WebP => ".webp",
            _ => throw new NotSupportedException($"不支持的图片格式: {format}")
        };
    }

    /// <summary>
    /// 根据图片格式获取MIME类型
    /// </summary>
    /// <param name="format">图片格式</param>
    /// <returns>MIME类型</returns>
    public static string GetMimeTypeFromFormat(ImageFormat format)
    {
        return format switch
        {
            ImageFormat.Jpeg => "image/jpeg",
            ImageFormat.Png => "image/png",
            ImageFormat.WebP => "image/webp",
            _ => throw new NotSupportedException($"不支持的图片格式: {format}")
        };
    }
}