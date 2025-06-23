using Foxel.Models.DataBase;
using Microsoft.EntityFrameworkCore;

namespace Foxel.Services.AI;

public class FaceClusteringService(
    IDbContextFactory<MyDbContext> contextFactory,
    ILogger<FaceClusteringService> logger) : IFaceClusteringService
{
    private const double BASE_SIMILARITY_THRESHOLD = 0.3;
    private const double HIGH_CONFIDENCE_THRESHOLD = 0.5;
    private const int MAX_COMPARISON_FACES = 10;

    public async Task<List<FaceCluster>> ClusterFacesAsync()
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        var unclusteredFaces = await dbContext.Faces
            .Where(f => f.Embedding != null && f.ClusterId == null)
            .Include(f => f.Picture)
            .ToListAsync();

        var clusters = new List<FaceCluster>();

        foreach (var face in unclusteredFaces)
        {
            var assignedCluster = await FindBestClusterAsync(face, clusters, dbContext);

            if (assignedCluster != null)
            {
                // 分配到现有聚类
                face.ClusterId = assignedCluster.Id;
            }
            else
            {
                // 创建新聚类
                var newCluster = new FaceCluster
                {
                    Name = $"未知人物 {clusters.Count + 1}",
                    CreatedAt = DateTime.UtcNow
                };

                dbContext.FaceClusters.Add(newCluster);
                await dbContext.SaveChangesAsync();

                face.ClusterId = newCluster.Id;
                clusters.Add(newCluster);
            }
        }

        await dbContext.SaveChangesAsync();
        logger.LogInformation("人脸聚类完成，共处理 {FaceCount} 个人脸，生成 {ClusterCount} 个聚类",
            unclusteredFaces.Count, clusters.Count);

        return clusters;
    }

    public async Task<FaceCluster?> AssignFaceToClusterAsync(int faceId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        var face = await dbContext.Faces
            .Include(f => f.Picture)
            .FirstOrDefaultAsync(f => f.Id == faceId);

        if (face?.Embedding == null) return null;

        // 获取所有现有聚类的代表人脸
        var existingClusters = await dbContext.FaceClusters
            .Include(c => c.Faces.Take(1))
            .ToListAsync();

        foreach (var cluster in existingClusters)
        {
            if (cluster.Faces?.Any() == true)
            {
                var representativeFace = cluster.Faces.First();
                if (representativeFace.Embedding != null)
                {
                    var similarity = CalculateSimilarity(face.Embedding, representativeFace.Embedding);
                    if (similarity >= BASE_SIMILARITY_THRESHOLD)
                    {
                        face.ClusterId = cluster.Id;
                        await dbContext.SaveChangesAsync();
                        return cluster;
                    }
                }
            }
        }

        // 创建新聚类
        var newCluster = new FaceCluster
        {
            Name = $"未知人物 {DateTime.Now:yyyyMMddHHmmss}",
            CreatedAt = DateTime.UtcNow
        };

        dbContext.FaceClusters.Add(newCluster);
        await dbContext.SaveChangesAsync();

        face.ClusterId = newCluster.Id;
        await dbContext.SaveChangesAsync();

        return newCluster;
    }

    public double CalculateSimilarity(float[] embedding1, float[] embedding2)
    {
        if (embedding1.Length != embedding2.Length) return 0;

        // 1. 余弦相似度
        double cosineSim = CalculateCosineSimilarity(embedding1, embedding2);
        
        // 2. 欧几里得距离转换为相似度
        double euclideanSim = CalculateEuclideanSimilarity(embedding1, embedding2);
        
        // 3. 曼哈顿距离转换为相似度
        double manhattanSim = CalculateManhattanSimilarity(embedding1, embedding2);
        
        // 加权组合多个相似度指标
        double weightedSimilarity = cosineSim * 0.6 + euclideanSim * 0.3 + manhattanSim * 0.1;
        
        return weightedSimilarity;
    }

    private double CalculateCosineSimilarity(float[] embedding1, float[] embedding2)
    {
        double dot = 0, norm1 = 0, norm2 = 0;

        for (int i = 0; i < embedding1.Length; i++)
        {
            dot += embedding1[i] * embedding2[i];
            norm1 += embedding1[i] * embedding1[i];
            norm2 += embedding2[i] * embedding2[i];
        }

        if (norm1 == 0 || norm2 == 0) return 0;
        return dot / (Math.Sqrt(norm1) * Math.Sqrt(norm2));
    }

    private double CalculateEuclideanSimilarity(float[] embedding1, float[] embedding2)
    {
        double sumSquareDiff = 0;
        for (int i = 0; i < embedding1.Length; i++)
        {
            double diff = embedding1[i] - embedding2[i];
            sumSquareDiff += diff * diff;
        }
        
        double distance = Math.Sqrt(sumSquareDiff);
        // 转换为相似度：距离越小，相似度越高
        return 1.0 / (1.0 + distance);
    }

    private double CalculateManhattanSimilarity(float[] embedding1, float[] embedding2)
    {
        double sumAbsDiff = 0;
        for (int i = 0; i < embedding1.Length; i++)
        {
            sumAbsDiff += Math.Abs(embedding1[i] - embedding2[i]);
        }
        
        // 转换为相似度
        return 1.0 / (1.0 + sumAbsDiff / embedding1.Length);
    }

    private async Task<FaceCluster?> FindBestClusterAsync(Face face, List<FaceCluster> newClusters, MyDbContext dbContext)
    {
        if (face.Embedding == null) return null;

        var clusterSimilarities = new List<(FaceCluster cluster, double avgSimilarity, double maxSimilarity, int comparisonCount)>();

        // 检查现有数据库中的聚类
        var existingClusters = await dbContext.FaceClusters
            .Include(c => c.Faces.Take(MAX_COMPARISON_FACES))
            .ToListAsync();

        foreach (var cluster in existingClusters.Concat(newClusters))
        {
            if (cluster.Faces?.Any() == true)
            {
                var similarities = new List<double>();
                
                foreach (var clusterFace in cluster.Faces.Take(MAX_COMPARISON_FACES))
                {
                    if (clusterFace.Embedding != null)
                    {
                        var similarity = CalculateSimilarity(face.Embedding, clusterFace.Embedding);
                        similarities.Add(similarity);
                    }
                }

                if (similarities.Any())
                {
                    double avgSimilarity = similarities.Average();
                    double maxSimilarity = similarities.Max();
                    
                    clusterSimilarities.Add((cluster, avgSimilarity, maxSimilarity, similarities.Count));
                }
            }
        }

        // 智能选择最佳聚类
        return SelectBestCluster(clusterSimilarities);
    }

    private FaceCluster? SelectBestCluster(List<(FaceCluster cluster, double avgSimilarity, double maxSimilarity, int comparisonCount)> clusterSimilarities)
    {
        if (!clusterSimilarities.Any()) return null;

        // 按照综合评分排序
        var rankedClusters = clusterSimilarities
            .Where(cs => cs.avgSimilarity >= BASE_SIMILARITY_THRESHOLD || cs.maxSimilarity >= HIGH_CONFIDENCE_THRESHOLD)
            .Select(cs => new
            {
                cs.cluster,
                cs.avgSimilarity,
                cs.maxSimilarity,
                cs.comparisonCount,
                // 综合评分：平均相似度权重60%，最高相似度权重30%，样本数量权重10%
                Score = cs.avgSimilarity * 0.6 + cs.maxSimilarity * 0.3 + 
                       Math.Min(cs.comparisonCount / (double)MAX_COMPARISON_FACES, 1.0) * 0.1
            })
            .OrderByDescending(x => x.Score)
            .ToList();

        if (!rankedClusters.Any()) return null;

        var bestMatch = rankedClusters.First();
        
        // 额外验证：如果最高相似度很高，直接接受
        if (bestMatch.maxSimilarity >= HIGH_CONFIDENCE_THRESHOLD)
        {
            return bestMatch.cluster;
        }

        // 如果平均相似度足够高且有足够样本，接受
        if (bestMatch.avgSimilarity >= BASE_SIMILARITY_THRESHOLD && bestMatch.comparisonCount >= 2)
        {
            return bestMatch.cluster;
        }

        return null;
    }

    public async Task<List<FaceCluster>> ClusterUserFacesAsync(int userId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();

        // 获取指定用户所有有嵌入向量但未分类的人脸
        var unclusteredFaces = await dbContext.Faces
            .Where(f => f.Embedding != null && f.ClusterId == null && f.Picture.UserId == userId)
            .Include(f => f.Picture)
            .ToListAsync();

        var clusters = new List<FaceCluster>();

        foreach (var face in unclusteredFaces)
        {
            var assignedCluster = await FindBestUserClusterAsync(face, userId, clusters, dbContext);

            if (assignedCluster != null)
            {
                face.ClusterId = assignedCluster.Id;
            }
            else
            {
                var newCluster = new FaceCluster
                {
                    Name = $"未知人物 {DateTime.Now:yyyyMMddHHmmss}",
                    CreatedAt = DateTime.UtcNow
                };

                dbContext.FaceClusters.Add(newCluster);
                await dbContext.SaveChangesAsync();

                face.ClusterId = newCluster.Id;
                clusters.Add(newCluster);
            }
        }

        await dbContext.SaveChangesAsync();
        logger.LogInformation("用户 {UserId} 人脸聚类完成，共处理 {FaceCount} 个人脸，生成 {ClusterCount} 个聚类",
            userId, unclusteredFaces.Count, clusters.Count);

        return clusters;
    }

    private async Task<FaceCluster?> FindBestUserClusterAsync(Face face, int userId, List<FaceCluster> newClusters, MyDbContext dbContext)
    {
        if (face.Embedding == null) return null;

        var clusterSimilarities = new List<(FaceCluster cluster, double avgSimilarity, double maxSimilarity, int comparisonCount)>();

        // 检查该用户现有的聚类
        var existingClusters = await dbContext.FaceClusters
            .Where(c => dbContext.Faces.Any(f => f.ClusterId == c.Id && f.Picture.UserId == userId))
            .Include(c => c.Faces.Where(f => f.Picture.UserId == userId).Take(MAX_COMPARISON_FACES))
            .ToListAsync();

        foreach (var cluster in existingClusters.Concat(newClusters))
        {
            if (cluster.Faces?.Any() == true)
            {
                var similarities = new List<double>();
                
                foreach (var clusterFace in cluster.Faces.Take(MAX_COMPARISON_FACES))
                {
                    if (clusterFace.Embedding != null)
                    {
                        var similarity = CalculateSimilarity(face.Embedding, clusterFace.Embedding);
                        similarities.Add(similarity);
                    }
                }

                if (similarities.Any())
                {
                    double avgSimilarity = similarities.Average();
                    double maxSimilarity = similarities.Max();
                    
                    clusterSimilarities.Add((cluster, avgSimilarity, maxSimilarity, similarities.Count));
                }
            }
        }

        return SelectBestCluster(clusterSimilarities);
    }

    // 新增：聚类质量评估方法
    public async Task<ClusterQualityMetrics> EvaluateClusterQualityAsync(int clusterId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();
        
        var cluster = await dbContext.FaceClusters
            .Include(c => c.Faces.Where(f => f.Embedding != null))
            .FirstOrDefaultAsync(c => c.Id == clusterId);

        if (cluster?.Faces == null || !cluster.Faces.Any())
        {
            return new ClusterQualityMetrics { IsValid = false };
        }

        var embeddings = cluster.Faces.Select(f => f.Embedding).Where(e => e != null).ToArray();
        if (embeddings.Length < 2)
        {
            return new ClusterQualityMetrics { IsValid = true, InternalSimilarity = 1.0, FaceCount = embeddings.Length };
        }

        // 计算内部相似度
        var similarities = new List<double>();
        for (int i = 0; i < embeddings.Length; i++)
        {
            for (int j = i + 1; j < embeddings.Length; j++)
            {
                similarities.Add(CalculateSimilarity(embeddings[i]!, embeddings[j]!));
            }
        }

        return new ClusterQualityMetrics
        {
            IsValid = true,
            InternalSimilarity = similarities.Average(),
            MinSimilarity = similarities.Min(),
            MaxSimilarity = similarities.Max(),
            FaceCount = embeddings.Length,
            SimilarityStandardDeviation = CalculateStandardDeviation(similarities)
        };
    }

    private double CalculateStandardDeviation(List<double> values)
    {
        if (!values.Any()) return 0;
        
        double mean = values.Average();
        double sumSquaredDifferences = values.Sum(v => Math.Pow(v - mean, 2));
        return Math.Sqrt(sumSquaredDifferences / values.Count);
    }

    // 新增：动态阈值调整
    public async Task<double> CalculateOptimalThresholdAsync(int userId)
    {
        await using var dbContext = await contextFactory.CreateDbContextAsync();
        
        var userClusters = await dbContext.FaceClusters
            .Where(c => dbContext.Faces.Any(f => f.ClusterId == c.Id && f.Picture.UserId == userId))
            .Include(c => c.Faces.Where(f => f.Picture.UserId == userId && f.Embedding != null))
            .ToListAsync();

        var intraClusterSimilarities = new List<double>();
        var interClusterSimilarities = new List<double>();

        // 计算聚类内相似度
        foreach (var cluster in userClusters.Where(c => c.Faces.Count > 1))
        {
            var faces = cluster.Faces.Where(f => f.Embedding != null).ToArray();
            for (int i = 0; i < faces.Length; i++)
            {
                for (int j = i + 1; j < faces.Length; j++)
                {
                    intraClusterSimilarities.Add(CalculateSimilarity(faces[i].Embedding!, faces[j].Embedding!));
                }
            }
        }

        // 计算聚类间相似度
        for (int i = 0; i < userClusters.Count; i++)
        {
            for (int j = i + 1; j < userClusters.Count; j++)
            {
                var cluster1Faces = userClusters[i].Faces.Where(f => f.Embedding != null).Take(5).ToArray();
                var cluster2Faces = userClusters[j].Faces.Where(f => f.Embedding != null).Take(5).ToArray();
                
                foreach (var face1 in cluster1Faces)
                {
                    foreach (var face2 in cluster2Faces)
                    {
                        interClusterSimilarities.Add(CalculateSimilarity(face1.Embedding!, face2.Embedding!));
                    }
                }
            }
        }

        if (!intraClusterSimilarities.Any() || !interClusterSimilarities.Any())
        {
            return BASE_SIMILARITY_THRESHOLD;
        }

        // 找到最优分割点
        double minIntra = intraClusterSimilarities.Min();
        double maxInter = interClusterSimilarities.Max();
        
        // 理想阈值应该在聚类间最大相似度和聚类内最小相似度之间
        double optimalThreshold = (minIntra + maxInter) / 2.0;
        
        // 确保在合理范围内
        return Math.Max(0.4, Math.Min(0.9, optimalThreshold));
    }
}

// 新增：聚类质量评估结果类
public class ClusterQualityMetrics
{
    public bool IsValid { get; set; }
    public double InternalSimilarity { get; set; }
    public double MinSimilarity { get; set; }
    public double MaxSimilarity { get; set; }
    public int FaceCount { get; set; }
    public double SimilarityStandardDeviation { get; set; }
}