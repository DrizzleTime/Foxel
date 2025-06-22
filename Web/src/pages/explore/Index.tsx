import React, { useState, useEffect, useCallback } from 'react';
import {
  Card, Button, Space, Modal, message, Typography,
  Row, Col, Form, Input, Avatar,
  Tag, Tooltip, Spin, Empty, Statistic,
  Select, Grid
} from 'antd';
import {
  UserOutlined, ReloadOutlined, PlayCircleOutlined,
  EditOutlined, TeamOutlined, MergeCellsOutlined,
  ExclamationCircleOutlined, EyeOutlined,
  HeartOutlined, SearchOutlined
} from '@ant-design/icons';
import {
  getMyFaceClusters, updateMyCluster, startMyFaceClustering, mergeMyUserClusters,
  getMyPicturesByCluster,
  type FaceClusterResponse, type UpdateClusterRequest
} from '../../api';
import type { PictureResponse } from '../../api/pictureApi';
import ImageGrid from '../../components/image/ImageGrid/ImageGrid';

const { Title, Text, Paragraph } = Typography;
const { confirm } = Modal;
const { useBreakpoint } = Grid;

const FaceExplore: React.FC = () => {
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  const [clusters, setClusters] = useState<FaceClusterResponse[]>([]);
  const [loading, setLoading] = useState(false);
  const [clusteringLoading, setClusteringLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize] = useState(12);

  const [isEditModalVisible, setIsEditModalVisible] = useState(false);
  const [isMergeModalVisible, setIsMergeModalVisible] = useState(false);
  const [isPictureModalVisible, setIsPictureModalVisible] = useState(false);
  const [editingCluster, setEditingCluster] = useState<FaceClusterResponse | null>(null);
  const [targetCluster, setTargetCluster] = useState<FaceClusterResponse | null>(null);
  const [clusterPictures, setClusterPictures] = useState<PictureResponse[]>([]);
  const [picturesLoading, setPicturesLoading] = useState(false);

  const [editForm] = Form.useForm<UpdateClusterRequest>();
  const [mergeForm] = Form.useForm();

  const fetchClusters = useCallback(async (page = currentPage) => {
    setLoading(true);
    try {
      const response = await getMyFaceClusters(page, pageSize);
      if (response.success) {
        const actualData = response.data?.data || response.data;
        setClusters(Array.isArray(actualData) ? actualData : []);
        setTotal(response.data?.totalCount || response.totalCount || 0);
      } else {
        message.error(response.message || '获取人脸聚类失败');
        setClusters([]);
        setTotal(0);
      }
    } catch (error) {
      message.error('获取人脸聚类失败，请检查网络连接');
      setClusters([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [currentPage, pageSize]);

  const fetchClusterPictures = useCallback(async (clusterId: number) => {
    setPicturesLoading(true);
    try {
      const response = await getMyPicturesByCluster(clusterId, 1, 100); // 增加获取数量
      if (response.success) {
        const actualData = response.data?.data || response.data;
        setClusterPictures(Array.isArray(actualData) ? actualData : []);
      } else {
        message.error(response.message || '获取聚类图片失败');
        setClusterPictures([]);
      }
    } catch (error) {
      message.error('获取聚类图片失败');
      setClusterPictures([]);
    } finally {
      setPicturesLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchClusters();
  }, [fetchClusters]);

  const handleLoadMore = () => {
    const nextPage = currentPage + 1;
    setCurrentPage(nextPage);
    fetchClusters(nextPage);
  };

  const showEditModal = (cluster: FaceClusterResponse) => {
    setEditingCluster(cluster);
    editForm.setFieldsValue({
      personName: cluster.personName,
      description: cluster.description,
    });
    setIsEditModalVisible(true);
  };

  const showMergeModal = (cluster: FaceClusterResponse) => {
    setTargetCluster(cluster);
    mergeForm.resetFields();
    setIsMergeModalVisible(true);
  };

  const showPicturesModal = (cluster: FaceClusterResponse) => {
    setEditingCluster(cluster);
    setIsPictureModalVisible(true);
    fetchClusterPictures(cluster.id);
  };

  const handleEditOk = async () => {
    if (!editingCluster) return;

    try {
      const values = await editForm.validateFields();
      setLoading(true);
      const response = await updateMyCluster(editingCluster.id, values);

      if (response.success) {
        message.success('更新聚类信息成功');
        setIsEditModalVisible(false);
        fetchClusters();
      } else {
        message.error(response.message || '更新失败');
      }
    } catch (errorInfo) {
      console.log('Validate Failed:', errorInfo);
    } finally {
      setLoading(false);
    }
  };

  const handleMergeOk = async () => {
    if (!targetCluster) return;

    try {
      const values = await mergeForm.validateFields();
      setLoading(true);
      const response = await mergeMyUserClusters(targetCluster.id, values.sourceClusterId);

      if (response.success) {
        message.success('合并聚类成功');
        setIsMergeModalVisible(false);
        fetchClusters();
      } else {
        message.error(response.message || '合并失败');
      }
    } catch (errorInfo) {
      console.log('Validate Failed:', errorInfo);
    } finally {
      setLoading(false);
    }
  };

  const handleStartClustering = () => {
    confirm({
      title: '开始人脸聚类分析',
      icon: <ExclamationCircleOutlined />,
      content: '这将分析您上传图片中的未分类人脸，帮助您找到相同的人物。可能需要一些时间，确定要开始吗？',
      async onOk() {
        setClusteringLoading(true);
        try {
          const response = await startMyFaceClustering();
          if (response.success) {
            message.success('人脸聚类任务已开始，请稍后刷新查看结果');
          } else {
            message.error(response.message || '启动聚类失败');
          }
        } catch (error) {
          message.error('启动聚类失败');
        } finally {
          setClusteringLoading(false);
        }
      }
    });
  };

  const renderClusterCard = (cluster: FaceClusterResponse) => (
    <Card
      key={cluster.id}
      hoverable
      className="cluster-card"
      cover={
        <div style={{
          height: 180,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#f8f9fa',
          overflow: 'hidden',
          padding: 20
        }}>
          {cluster.thumbnailPath ? (
            <Avatar
              size={120}
              src={cluster.thumbnailPath}
              style={{
                border: '3px solid #fff',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
              }}
            />
          ) : (
            <Avatar
              size={120}
              icon={<UserOutlined />}
              style={{
                backgroundColor: '#e6f7ff',
                border: '3px solid #fff',
                boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
              }}
            />
          )}
        </div>
      }
      actions={[
        <Tooltip title="查看图片" key="view">
          <EyeOutlined onClick={() => showPicturesModal(cluster)} />
        </Tooltip>,
        <Tooltip title="编辑信息" key="edit">
          <EditOutlined onClick={() => showEditModal(cluster)} />
        </Tooltip>,
        <Tooltip title="合并聚类" key="merge">
          <MergeCellsOutlined onClick={() => showMergeModal(cluster)} />
        </Tooltip>
      ]}
    >
      <Card.Meta
        title={
          <div>
            <Text strong>{cluster.name}</Text>
            <Tag color="blue" style={{ marginLeft: 8 }}>
              {cluster.faceCount} 张人脸
            </Tag>
          </div>
        }
        description={
          <div>
            {cluster.personName && (
              <Paragraph style={{ margin: 0, color: '#52c41a' }}>
                <HeartOutlined /> {cluster.personName}
              </Paragraph>
            )}
            {cluster.description && (
              <Paragraph
                style={{ margin: '8px 0 0 0' }}
                ellipsis={{ rows: 2, tooltip: cluster.description }}
              >
                {cluster.description}
              </Paragraph>
            )}
            <Text type="secondary" style={{ fontSize: '12px' }}>
              最后更新: {new Date(cluster.lastUpdatedAt).toLocaleDateString()}
            </Text>
          </div>
        }
      />
    </Card>
  );

  return (
    <div className="face-explore" style={{ padding: isMobile ? 16 : 24 }}>
      {/* 页面头部 */}
      <div style={{ marginBottom: 24 }}>
        <Row align="middle" justify="space-between" gutter={[16, 16]}>
          <Col>
            <Space align="center">
              <SearchOutlined style={{ fontSize: 28, color: '#1890ff' }} />
              <div>
                <Title level={2} style={{ margin: 0 }}>人脸探索</Title>
                <Text type="secondary">
                  发现和管理您照片中的人物，为每个聚类命名和整理
                </Text>
              </div>
            </Space>
          </Col>
          <Col>
            <Space>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                onClick={handleStartClustering}
                loading={clusteringLoading}
              >
                开始聚类分析
              </Button>
              <Button
                icon={<ReloadOutlined />}
                onClick={() => fetchClusters()}
                loading={loading}
              >
                刷新
              </Button>
            </Space>
          </Col>
        </Row>
      </div>

      {/* 统计信息 */}
      <Row gutter={16} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={8} md={6}>
          <Card>
            <Statistic
              title="人脸聚类"
              value={total}
              prefix={<TeamOutlined />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card>
            <Statistic
              title="已命名聚类"
              value={clusters.filter(c => c.personName).length}
              prefix={<HeartOutlined />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} md={6}>
          <Card>
            <Statistic
              title="总人脸数"
              value={clusters.reduce((sum, c) => sum + c.faceCount, 0)}
              prefix={<UserOutlined />}
              valueStyle={{ color: '#722ed1' }}
            />
          </Card>
        </Col>
      </Row>

      {/* 聚类网格 */}
      <Spin spinning={loading}>
        {clusters.length > 0 ? (
          <>
            <Row gutter={[16, 16]}>
              {clusters.map(cluster => (
                <Col xs={24} sm={12} md={8} lg={6} xl={4} key={cluster.id}>
                  {renderClusterCard(cluster)}
                </Col>
              ))}
            </Row>

            {/* 加载更多按钮 */}
            {clusters.length < total && (
              <div style={{ textAlign: 'center', marginTop: 24 }}>
                <Button size="large" onClick={handleLoadMore} loading={loading}>
                  加载更多 ({clusters.length} / {total})
                </Button>
              </div>
            )}
          </>
        ) : (
          <Empty
            description={
              <div>
                <Paragraph>还没有发现人脸聚类</Paragraph>
                <Paragraph type="secondary">
                  点击"开始聚类分析"来分析您的照片并发现其中的人物
                </Paragraph>
              </div>
            }
            image={Empty.PRESENTED_IMAGE_SIMPLE}
          >
            <Button
              type="primary"
              icon={<PlayCircleOutlined />}
              onClick={handleStartClustering}
              loading={clusteringLoading}
            >
              开始聚类分析
            </Button>
          </Empty>
        )}
      </Spin>

      {/* 编辑聚类模态框 */}
      <Modal
        title="编辑聚类信息"
        open={isEditModalVisible}
        onOk={handleEditOk}
        onCancel={() => setIsEditModalVisible(false)}
        confirmLoading={loading}
        destroyOnClose
      >
        <Form form={editForm} layout="vertical">
          <Form.Item name="personName" label="人物姓名">
            <Input placeholder="请输入人物姓名，如：张三、妈妈、小明等" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea rows={3} placeholder="请输入描述信息，如：大学同学、家人等" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 合并聚类模态框 */}
      <Modal
        title={`合并聚类到: ${targetCluster?.personName || targetCluster?.name || ''}`}
        open={isMergeModalVisible}
        onOk={handleMergeOk}
        onCancel={() => setIsMergeModalVisible(false)}
        confirmLoading={loading}
        destroyOnClose
      >
        <Form form={mergeForm} layout="vertical">
          <Form.Item
            name="sourceClusterId"
            label="选择要合并的聚类"
            rules={[{ required: true, message: '请选择要合并的聚类' }]}
          >
            <Select
              placeholder="请选择要合并的聚类"
              showSearch
              optionFilterProp="children"
              filterOption={(input: string, option: any) =>
                (option?.label ?? '').toLowerCase().includes(input.toLowerCase())
              }
              options={clusters
                .filter(c => c.id !== targetCluster?.id)
                .map(c => ({
                  value: c.id,
                  label: `${c.personName || c.name} (${c.faceCount} 个人脸)`,
                }))}
            />
          </Form.Item>
          <Text type="secondary">
            合并后，选择的聚类将被删除，其所有人脸将移动到目标聚类中。
          </Text>
        </Form>
      </Modal>

      {/* 查看聚类图片模态框 */}
      <Modal
        title={`${editingCluster?.personName || editingCluster?.name || ''} 的照片`}
        open={isPictureModalVisible}
        onCancel={() => setIsPictureModalVisible(false)}
        footer={null}
        width="90vw"
        style={{ maxWidth: 1200 }}
        destroyOnClose
      >
        <div style={{ 
          maxHeight: '70vh', 
          overflowY: 'auto',
          padding: '16px 0'
        }}>
          <ImageGrid
            dataSource={clusterPictures}
            loading={picturesLoading}
            emptyText="该聚类中暂无图片"
            showPagination={false}
            pageSize={50}
            selectable={false}
            queryParams={{}}
          />
        </div>
      </Modal>

    </div>
  );
};

export default FaceExplore;
