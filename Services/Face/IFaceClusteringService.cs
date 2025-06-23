using Foxel.Models.DataBase;

namespace Foxel.Services.AI;

public interface IFaceClusteringService
{
    /// <summary>
    /// 对所有未分类的人脸进行聚类
    /// </summary>
    Task<List<FaceCluster>> ClusterFacesAsync();
    
    /// <summary>
    /// 对指定用户的未分类人脸进行聚类
    /// </summary>
    Task<List<FaceCluster>> ClusterUserFacesAsync(int userId);
    
    /// <summary>
    /// 为新检测到的人脸分配到现有聚类或创建新聚类
    /// </summary>
    Task<FaceCluster?> AssignFaceToClusterAsync(int faceId);
    
    /// <summary>
    /// 计算两个人脸嵌入向量的相似度
    /// </summary>
    double CalculateSimilarity(float[] embedding1, float[] embedding2);
}