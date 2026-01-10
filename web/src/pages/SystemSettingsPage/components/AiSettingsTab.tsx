import {
  Alert,
  Button,
  Card,
  Col,
  Checkbox,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  List,
  Modal,
  Row,
  Select,
  Space,
  Tag,
  Tooltip,
  Typography,
  Steps,
  Tabs,
  message,
} from 'antd';
import {
  ArrowLeftOutlined,
  ArrowRightOutlined,
  AppstoreOutlined,
  BuildOutlined,
  CopyOutlined,
  DeleteOutlined,
  EditOutlined,
  EyeOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SoundOutlined,
  SortAscendingOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import type {
  AIDefaultAssignments,
  AIDefaultModels,
  AIAbility,
  AIModel,
  AIModelPayload,
  AIProvider,
  AIProviderPayload,
} from '../../../api/aiProviders';
import {
  createModel,
  createProvider,
  deleteModel,
  deleteProvider,
  fetchDefaults,
  fetchProviders,
  fetchRemoteModels,
  updateDefaults,
  updateModel,
  updateProvider,
} from '../../../api/aiProviders';
import { useI18n } from '../../../i18n';
import '../../../styles/ai-settings.css';

type ProviderModalState = {
  open: boolean;
  step: 1 | 2;
  editing?: AIProvider | null;
};

type ModelModalState = {
  open: boolean;
  provider?: AIProvider | null;
  editing?: AIModel | null;
};

interface ProviderTemplate {
  key: string;
  nameKey: string;
  descriptionKey: string;
  api_format: 'openai' | 'gemini';
  identifier: string;
  base_url?: string;
  logo_url?: string;
  provider_type?: string;
  doc_url?: string;
  allow_format_switch?: boolean;
}

const abilityOrder: AIAbility[] = ['chat', 'vision', 'embedding', 'rerank', 'voice', 'tools'];

const abilityInfo: Record<AIAbility, { icon: ReactNode; label: string; color: string; description: string }> = {
  chat: {
    icon: <MessageOutlined />,
    label: 'Main Chat Model',
    color: 'purple',
    description: 'Primary assistant for conversations, reasoning, and tool calls.',
  },
  vision: {
    icon: <EyeOutlined />,
    label: 'Vision Model',
    color: 'geekblue',
    description: 'Handles multimodal perception such as image understanding.',
  },
  embedding: {
    icon: <AppstoreOutlined />,
    label: 'Embedding Model',
    color: 'gold',
    description: 'Transforms content into dense vectors for search and retrieval.',
  },
  rerank: {
    icon: <SortAscendingOutlined />,
    label: 'Rerank Model',
    color: 'cyan',
    description: 'Optimises ranking quality for search candidates.',
  },
  voice: {
    icon: <SoundOutlined />,
    label: 'Voice Model',
    color: 'orange',
    description: 'Covers text-to-speech and speech understanding scenarios.',
  },
  tools: {
    icon: <ToolOutlined />,
    label: 'Tools Model',
    color: 'magenta',
    description: 'Supports function calling, orchestration, and automation.',
  },
};

const providerTemplates: ProviderTemplate[] = [
  {
    key: 'custom-provider',
    nameKey: 'Custom Provider',
    descriptionKey: 'Custom Provider Description',
    api_format: 'openai',
    identifier: 'custom-provider',
    allow_format_switch: true,
  },
  {
    key: 'openai',
    nameKey: 'OpenAI Provider',
    descriptionKey: 'OpenAI Provider Description',
    api_format: 'openai',
    identifier: 'openai',
    base_url: 'https://api.openai.com/v1',
    logo_url: '/icon/openai.svg',
    provider_type: 'builtin',
    doc_url: 'https://platform.openai.com/docs/api-reference',
  },
  {
    key: 'google-ai',
    nameKey: 'Google AI Provider',
    descriptionKey: 'Google AI Provider Description',
    api_format: 'gemini',
    identifier: 'google-ai',
    base_url: 'https://generativelanguage.googleapis.com/v1beta',
    logo_url: '/icon/gemini-color.svg',
    provider_type: 'builtin',
    doc_url: 'https://ai.google.dev/api/rest',
  },
  {
    key: 'siliconflow',
    nameKey: 'SiliconFlow Provider',
    descriptionKey: 'SiliconFlow Provider Description',
    api_format: 'openai',
    identifier: 'siliconflow',
    base_url: 'https://api.siliconflow.cn/v1',
    logo_url: '/icon/siliconcloud-color.svg',
    provider_type: 'builtin',
    doc_url: 'https://docs.siliconflow.cn/',
  },
  {
    key: 'deepseek',
    nameKey: 'DeepSeek Provider',
    descriptionKey: 'DeepSeek Provider Description',
    api_format: 'openai',
    identifier: 'deepseek',
    base_url: 'https://api.deepseek.com/v1',
    logo_url: '/icon/deepseek-color.svg',
    provider_type: 'builtin',
    doc_url: 'https://platform.deepseek.com/api-docs',
  },
];

const abilityTagColor: Record<AIAbility, string> = {
  chat: 'purple',
  vision: 'geekblue',
  embedding: 'gold',
  rerank: 'cyan',
  voice: 'orange',
  tools: 'magenta',
};

type AIProviderFormValues = {
  name?: string;
  identifier?: string;
  api_format: AIProviderPayload['api_format'];
  base_url?: string;
  api_key?: string;
  logo_url?: string;
  provider_type?: string;
};

type AIModelFormValues = Omit<AIModelPayload, 'metadata'>;

interface RemoteModelCandidate extends AIModelPayload {
  exists: boolean;
}

const { Title, Text } = Typography;

export default function AiSettingsTab() {
  const { t } = useI18n();
  const [providers, setProviders] = useState<AIProvider[]>([]);
  const [defaults, setDefaults] = useState<AIDefaultModels>({});
  const [defaultSelections, setDefaultSelections] = useState<AIDefaultAssignments>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [savingDefaults, setSavingDefaults] = useState<boolean>(false);
  const [providerModal, setProviderModal] = useState<ProviderModalState>({ open: false, step: 1 });
  const [modelModal, setModelModal] = useState<ModelModalState>({ open: false });
  const [selectedTemplate, setSelectedTemplate] = useState<ProviderTemplate | null>(null);
  const [providerForm] = Form.useForm<AIProviderFormValues>();
  const [modelForm] = Form.useForm<AIModelFormValues>();
  const [modelMetadata, setModelMetadata] = useState<Record<string, unknown> | null>(null);
  const [remoteModels, setRemoteModels] = useState<RemoteModelCandidate[]>([]);
  const [selectedRemoteModels, setSelectedRemoteModels] = useState<string[]>([]);
  const [pullingRemoteModels, setPullingRemoteModels] = useState<boolean>(false);
  const [addingRemoteModels, setAddingRemoteModels] = useState<boolean>(false);
  const [modelModalTab, setModelModalTab] = useState<'remote' | 'manual'>('remote');
  const [remoteSearchKeyword, setRemoteSearchKeyword] = useState<string>('');
  const capabilitiesValue = Form.useWatch('capabilities', modelForm);
  const showEmbeddingDimensions = useMemo(() => {
    const capabilities = Array.isArray(capabilitiesValue) ? capabilitiesValue : [];
    return capabilities.includes('embedding') || capabilities.includes('rerank');
  }, [capabilitiesValue]);

  useEffect(() => {
    if (!showEmbeddingDimensions) {
      modelForm.setFieldsValue({ embedding_dimensions: null });
    }
  }, [modelForm, showEmbeddingDimensions]);

  const filteredRemoteModels = useMemo(() => {
    const keyword = remoteSearchKeyword.trim().toLowerCase();
    if (!keyword) {
      return remoteModels;
    }
    return remoteModels.filter((item) => {
      const name = (item.name || '').toLowerCase();
      const displayName = (item.display_name || '').toLowerCase();
      return name.includes(keyword) || displayName.includes(keyword);
    });
  }, [remoteModels, remoteSearchKeyword]);

  const refreshData = useCallback(async () => {
    setLoading(true);
    try {
      const [providerList, defaultMap] = await Promise.all([
        fetchProviders(),
        fetchDefaults(),
      ]);
      setProviders(providerList.map((item) => ({
        ...item,
        models: (item.models || []).sort((a, b) => a.name.localeCompare(b.name)),
      })));
      setDefaults(defaultMap);
      const initialSelections: AIDefaultAssignments = {};
      abilityOrder.forEach((ability) => {
        const model = defaultMap[ability];
        initialSelections[ability] = model ? model.id : null;
      });
      setDefaultSelections(initialSelections);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(msg || t('Load failed'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void refreshData();
  }, [refreshData]);

  const handleOpenProviderModal = (existing?: AIProvider | null) => {
    if (existing) {
      setProviderModal({ open: true, editing: existing, step: 2 });
      const matchedTemplate = providerTemplates.find((item) => item.identifier === existing.identifier) ?? null;
      setSelectedTemplate(matchedTemplate);
      providerForm.setFieldsValue({
        name: existing.name,
        identifier: existing.identifier,
        api_format: existing.api_format,
        base_url: existing.base_url ?? undefined,
        api_key: '',
        logo_url: existing.logo_url ?? undefined,
        provider_type: existing.provider_type ?? undefined,
      });
    } else {
      providerForm.resetFields();
      providerForm.setFieldsValue({ api_format: 'openai' });
      setSelectedTemplate(null);
      setProviderModal({ open: true, step: 1 });
    }
  };

  const handleCloseProviderModal = () => {
    setProviderModal({ open: false, step: 1 });
    setSelectedTemplate(null);
    providerForm.resetFields();
  };

  const handleTemplateSelect = (template: ProviderTemplate) => {
    setSelectedTemplate(template);
    setProviderModal((prev) => ({ ...prev, step: 2 }));
    providerForm.setFieldsValue({
      name: t(template.nameKey),
      identifier: template.identifier,
      api_format: template.api_format,
      base_url: template.base_url ?? '',
      api_key: '',
      logo_url: template.logo_url ?? '',
      provider_type: template.provider_type ?? '',
    });
  };

  const handleBackToTemplateStep = () => {
    setProviderModal((prev) => ({ ...prev, step: 1, editing: undefined }));
    setSelectedTemplate(null);
    providerForm.resetFields();
    providerForm.setFieldsValue({ api_format: 'openai' });
  };

  const handleSubmitProvider = async () => {
    const values = await providerForm.validateFields();
    const trimmedBaseUrl = values.base_url?.trim();
    const trimmedApiKey = values.api_key?.trim();
    const trimmedLogoUrl = values.logo_url?.trim();
    const trimmedProviderType = values.provider_type?.trim();
    const payload: AIProviderPayload = {
      name: (values.name || '').trim(),
      identifier: (values.identifier || '').trim(),
      api_format: values.api_format,
      base_url: trimmedBaseUrl ? trimmedBaseUrl : null,
      logo_url: trimmedLogoUrl ? trimmedLogoUrl : null,
      provider_type: trimmedProviderType ? trimmedProviderType : null,
    };
    if (trimmedApiKey) {
      payload.api_key = trimmedApiKey;
    }
    try {
      if (providerModal.editing) {
        await updateProvider(providerModal.editing.id, payload);
        message.success(t('Updated successfully'));
      } else {
        await createProvider(payload);
        message.success(t('Created successfully'));
      }
      handleCloseProviderModal();
      await refreshData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(msg || t('Save failed'));
    }
  };

  const handleDeleteProvider = (provider: AIProvider) => {
    Modal.confirm({
      title: t('Delete provider?'),
      content: t('Deleting this provider will also remove all associated models. Continue?'),
      okText: t('Confirm'),
      cancelText: t('Cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteProvider(provider.id);
          message.success(t('Deleted successfully'));
          await refreshData();
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          message.error(msg || t('Delete failed'));
        }
      },
    });
  };

  const handleOpenModelModal = (provider: AIProvider, editing?: AIModel | null) => {
    setModelModal({ open: true, provider, editing });
    setRemoteModels([]);
    setSelectedRemoteModels([]);
    setPullingRemoteModels(false);
    setAddingRemoteModels(false);
    setModelModalTab(editing ? 'manual' : 'remote');
    setRemoteSearchKeyword('');
    if (editing) {
      modelForm.setFieldsValue({
        name: editing.name,
        display_name: editing.display_name,
        description: editing.description,
        capabilities: editing.capabilities || [],
        context_window: editing.context_window,
        embedding_dimensions: editing.embedding_dimensions,
      });
      setModelMetadata(editing.metadata ?? null);
    } else {
      modelForm.resetFields();
      modelForm.setFieldValue('capabilities', []);
      setModelMetadata(null);
    }
  };

  const handleCloseModelModal = () => {
    setModelModal({ open: false });
    modelForm.resetFields();
    setModelMetadata(null);
    setRemoteModels([]);
    setSelectedRemoteModels([]);
    setPullingRemoteModels(false);
    setAddingRemoteModels(false);
    setModelModalTab('remote');
    setRemoteSearchKeyword('');
  };

  const handlePullRemoteModels = async () => {
    if (!modelModal.provider) return;
    setPullingRemoteModels(true);
    try {
      const { models: remoteList } = await fetchRemoteModels(modelModal.provider.id);
      const existingNames = new Set((modelModal.provider.models || []).map((item) => item.name));
      const mapped = remoteList.map<RemoteModelCandidate>((item) => ({
        ...item,
        metadata: item.metadata ?? null,
        exists: existingNames.has(item.name),
      }));
      if (!mapped.length) {
        message.info(t('No remote models found'));
      }
      setRemoteModels(mapped);
      setSelectedRemoteModels([]);
      setRemoteSearchKeyword('');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(msg || t('Fetch failed'));
    } finally {
      setPullingRemoteModels(false);
    }
  };

  const handleToggleRemoteSelection = (name: string, checked: boolean) => {
    setSelectedRemoteModels((prev) => {
      if (checked) {
        return prev.includes(name) ? prev : [...prev, name];
      }
      return prev.filter((item) => item !== name);
    });
  };

  const handleAddRemoteModels = async () => {
    if (!modelModal.provider) return;
    const candidates = remoteModels.filter(
      (item) => !item.exists && selectedRemoteModels.includes(item.name),
    );
    if (!candidates.length) {
      message.warning(t('Select models to add'));
      return;
    }
    setAddingRemoteModels(true);
    try {
      await Promise.all(candidates.map(async (item) => {
        const { exists, ...candidate } = item;
        void exists;
        const payload: AIModelPayload = {
          ...candidate,
          metadata: candidate.metadata ?? null,
        };
        await createModel(modelModal.provider!.id, payload);
      }));
      message.success(t('Added {count} models', { count: candidates.length }));
      handleCloseModelModal();
      await refreshData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(msg || t('Save failed'));
    } finally {
      setAddingRemoteModels(false);
    }
  };

  const renderManualModelForm = () => (
    <Form layout="vertical" form={modelForm}>
      {!modelModal.editing && (
        <Form.Item
          name="name"
          label={t('Model Identifier')}
          rules={[{ required: true, message: t('Enter model identifier') }]}
        >
          <Input placeholder="例如 gpt-4o-mini 或 models/gemini-1.5-flash" />
        </Form.Item>
      )}
      {modelModal.editing && (
        <Form.Item label={t('Model Identifier')}>
          <Input value={modelModal.editing.name} disabled />
        </Form.Item>
      )}
      <Form.Item name="display_name" label={t('Display Name')}>
        <Input />
      </Form.Item>
      <Form.Item name="description" label={t('Description')}>
        <Input.TextArea rows={3} />
      </Form.Item>
      <Form.Item name="capabilities" label={t('Capabilities')}>
        <Select
          mode="multiple"
          allowClear
          options={abilityOrder.map((ability) => ({
            value: ability,
            label: t(abilityInfo[ability].label),
          }))}
        />
      </Form.Item>
      <Row gutter={16}>
        <Col span={showEmbeddingDimensions ? 12 : 24}>
          <Form.Item name="context_window" label={t('Context Window')}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
        </Col>
        {showEmbeddingDimensions ? (
          <Col span={12}>
            <Form.Item name="embedding_dimensions" label={t('Embedding Dimensions')}>
              <InputNumber style={{ width: '100%' }} min={0} />
            </Form.Item>
          </Col>
        ) : null}
      </Row>
    </Form>
  );

  const renderRemoteModelsTab = () => (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap>
        <Button
          icon={<ReloadOutlined />}
          loading={pullingRemoteModels}
          onClick={handlePullRemoteModels}
          disabled={!modelModal.provider || addingRemoteModels}
        >
          {t('Pull Models')}
        </Button>
        {remoteModels.length > 0 ? (
          <Button
            onClick={() => {
              setRemoteModels([]);
              setSelectedRemoteModels([]);
              setRemoteSearchKeyword('');
            }}
            disabled={pullingRemoteModels || addingRemoteModels}
          >
            {t('Clear Remote List')}
          </Button>
        ) : null}
      </Space>
      {remoteModels.length > 0 ? (
        <>
          <Input
            allowClear
            placeholder={t('Search fetched models')}
            value={remoteSearchKeyword}
            onChange={(event) => setRemoteSearchKeyword(event.target.value)}
          />
          <div className="fx-ai-remote-models">
            <Alert type="info" message={t('Select models from the list to add them automatically')} showIcon />
            <List
              size="small"
              dataSource={filteredRemoteModels}
              locale={{
                emptyText: remoteSearchKeyword.trim()
                  ? t('No remote models match search')
                  : t('No remote models'),
              }}
              renderItem={(item) => {
                const disabled = item.exists;
                const checked = selectedRemoteModels.includes(item.name);
                return (
                  <List.Item
                    key={item.name}
                    className="fx-ai-remote-item"
                    actions={disabled ? [<Tag key="exists" color="default">{t('Already Added')}</Tag>] : undefined}
                  >
                    <Checkbox
                      checked={checked}
                      disabled={disabled || addingRemoteModels}
                      onChange={(event) => handleToggleRemoteSelection(item.name, event.target.checked)}
                    >
                      <div className="fx-ai-remote-item-main">
                        <Text strong>{item.display_name || item.name}</Text>
                        {item.description ? (
                          <div className="fx-ai-remote-desc">{item.description}</div>
                        ) : null}
                        <Space size={4} wrap>
                          {(item.capabilities || []).map((cap) => (
                            <Tag key={cap} color={abilityTagColor[cap as AIAbility]}>
                              {cap.toUpperCase()}
                            </Tag>
                          ))}
                        </Space>
                        <Space size={12} className="fx-ai-model-metrics">
                          {item.context_window ? <span><CopyOutlined /> {item.context_window} tokens</span> : null}
                          {item.embedding_dimensions ? <span><BuildOutlined /> {item.embedding_dimensions} dims</span> : null}
                        </Space>
                      </div>
                    </Checkbox>
                  </List.Item>
                );
              }}
            />
          </div>
          <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
            <Button
              type="primary"
              onClick={handleAddRemoteModels}
              loading={addingRemoteModels}
              disabled={addingRemoteModels || !selectedRemoteModels.length}
            >
              {t('Add Selected Models')}
            </Button>
          </Space>
        </>
      ) : null}
    </Space>
  );

  const handleSubmitModel = async () => {
    const values = await modelForm.validateFields();
    if (!showEmbeddingDimensions) {
      values.embedding_dimensions = null;
    }
    const payload: AIModelPayload = {
      ...values,
      metadata: modelMetadata ?? null,
    };
    if (!modelModal.provider) return;
    try {
      if (modelModal.editing) {
        await updateModel(modelModal.editing.id, payload);
        message.success(t('Updated successfully'));
      } else {
        await createModel(modelModal.provider.id, payload);
        message.success(t('Created successfully'));
      }
      handleCloseModelModal();
      await refreshData();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      message.error(msg || t('Save failed'));
    }
  };

  const handleDeleteModel = (model: AIModel) => {
    Modal.confirm({
      title: t('Delete model?'),
      content: t('This operation cannot be undone. Continue?'),
      okText: t('Confirm'),
      cancelText: t('Cancel'),
      okButtonProps: { danger: true },
      onOk: async () => {
        try {
          await deleteModel(model.id);
          message.success(t('Deleted successfully'));
          await refreshData();
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err);
          message.error(msg || t('Delete failed'));
        }
      },
    });
  };

  const updateSelection = (ability: AIAbility, value: number | null) => {
    setDefaultSelections((prev) => ({
      ...prev,
      [ability]: value ?? null,
    }));
  };

  const allModels = useMemo(() => {
    const map = new Map<number, AIModel>();
    providers.forEach((provider) => {
      (provider.models || []).forEach((model) => {
        map.set(model.id, { ...model, provider });
      });
    });
    return map;
  }, [providers]);

  const collectionsByAbility = (ability: AIAbility) => {
    return providers
      .map((provider) => {
        const models = (provider.models || []).filter((model) => (model.capabilities || []).includes(ability));
        if (!models.length) return null;
        return {
          label: (
            <div className="fx-ai-provider-option">
              {provider.logo_url ? (
                <img src={provider.logo_url} alt={provider.name} />
              ) : (
                <RobotOutlined style={{ marginRight: 8 }} />
              )}
              <span>{provider.name}</span>
            </div>
          ),
          options: models.map((model) => ({
            value: model.id,
            label: (
              <div className="fx-ai-model-option">
                <span className="fx-ai-model-name">{model.display_name || model.name}</span>
                <span className="fx-ai-model-provider-tag">{provider.name}</span>
              </div>
            ),
          })),
        };
      })
      .filter(Boolean) as Array<{ label: ReactNode; options: Array<{ value: number; label: ReactNode }> }>;
  };

  const handleSaveDefaults = async () => {
    const previousEmbedding = defaults.embedding?.id ?? null;
    const nextEmbedding = defaultSelections.embedding ?? null;
    const previousEmbeddingModel = previousEmbedding ? allModels.get(previousEmbedding) : undefined;
    const nextEmbeddingModel = nextEmbedding ? allModels.get(nextEmbedding) : undefined;
    const dimensionChanged = previousEmbeddingModel && nextEmbeddingModel
      && previousEmbeddingModel.embedding_dimensions
      && nextEmbeddingModel.embedding_dimensions
      && previousEmbeddingModel.embedding_dimensions !== nextEmbeddingModel.embedding_dimensions;

    const proceed = async () => {
      setSavingDefaults(true);
      try {
        const result = await updateDefaults(defaultSelections);
        setDefaults(result);
        const nextSelections: AIDefaultAssignments = {};
        abilityOrder.forEach((ability) => {
          const model = result[ability];
          nextSelections[ability] = model ? model.id : null;
        });
        setDefaultSelections(nextSelections);
        message.success(t('Saved successfully'));
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        message.error(msg || t('Save failed'));
      } finally {
        setSavingDefaults(false);
      }
    };

    if (previousEmbedding !== nextEmbedding && dimensionChanged) {
      Modal.confirm({
        title: t('Confirm embedding dimension change'),
        content: t('Changing the embedding dimension will clear the vector database automatically. Continue?'),
        okText: t('Confirm'),
        cancelText: t('Cancel'),
        onOk: proceed,
      });
      return;
    }
    await proceed();
  };

  const renderProviderCard = (provider: AIProvider) => {
    const models = provider.models || [];
    return (
      <Card
        key={provider.id}
        className="fx-ai-provider-card"
        title={(
          <div className="fx-ai-provider-header">
            <div className="fx-ai-provider-meta">
              {provider.logo_url ? (
                <img src={provider.logo_url} alt={provider.name} className="fx-ai-provider-logo" />
              ) : (
                <RobotOutlined className="fx-ai-provider-logo" />
              )}
              <div>
                <Text className="fx-ai-provider-name">{provider.name}</Text>
                <div className="fx-ai-provider-sub">
                  <Tag color="blue">{provider.api_format.toUpperCase()} API</Tag>
                  {provider.base_url && (
                    <Tooltip title={provider.base_url}>
                      <Text type="secondary" ellipsis style={{ maxWidth: 180 }}>
                        {provider.base_url}
                      </Text>
                    </Tooltip>
                  )}
                </div>
              </div>
            </div>
          </div>
        )}
        extra={(
          <Space className="fx-ai-provider-actions" size={8} wrap>
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => handleOpenModelModal(provider)}
            >
              {t('Add Model')}
            </Button>
            <Button
              icon={<EditOutlined />}
              onClick={() => handleOpenProviderModal(provider)}
              shape="circle"
              aria-label={t('Edit Provider')}
            />
            <Button
              icon={<DeleteOutlined />}
              danger
              onClick={() => handleDeleteProvider(provider)}
              shape="circle"
              aria-label={t('Delete Provider')}
            />
          </Space>
        )}
      >
        {models.length === 0 ? (
          <Empty description={t('No models yet')} />
        ) : (
          <div className="fx-ai-model-list">
            {models.map((model) => (
              <div key={model.id} className="fx-ai-model-item">
                <div className="fx-ai-model-info">
                  <div className="fx-ai-model-header">
                    <Title level={5} className="fx-ai-model-title">{model.display_name || model.name}</Title>
                    {(model.capabilities || []).length ? (
                      <Space size={4} wrap className="fx-ai-model-tags">
                        {(model.capabilities || []).map((cap) => (
                          <Tag key={cap} color={abilityTagColor[cap as AIAbility]}>
                            {cap.toUpperCase()}
                          </Tag>
                        ))}
                      </Space>
                    ) : null}
                  </div>
                  <div className="fx-ai-model-meta">
                    <Text type="secondary" className="fx-ai-model-desc">
                      {model.description || model.name}
                    </Text>
                    <Space size={10} className="fx-ai-model-metrics" wrap>
                      {model.context_window ? <span><CopyOutlined /> {model.context_window} tokens</span> : null}
                      {model.embedding_dimensions ? <span><BuildOutlined /> {model.embedding_dimensions} dims</span> : null}
                    </Space>
                  </div>
                </div>
                <Space className="fx-ai-model-actions">
                  <Button size="small" icon={<EditOutlined />} onClick={() => handleOpenModelModal(provider, model)} />
                  <Button size="small" icon={<DeleteOutlined />} danger onClick={() => handleDeleteModel(model)} />
                </Space>
              </div>
            ))}
          </div>
        )}
      </Card>
    );
  };

  const stepItems = useMemo(() => ([
    { title: t('Choose Template') },
    { title: t('Configure Provider') },
  ]), [t]);

  const activeTemplate = useMemo(() => {
    if (selectedTemplate) {
      return selectedTemplate;
    }
    if (providerModal.editing) {
      return providerTemplates.find((tpl) => tpl.identifier === providerModal.editing?.identifier) ?? null;
    }
    return null;
  }, [selectedTemplate, providerModal.editing]);

  const allowFormatChange = useMemo(() => {
    if (providerModal.editing) {
      return false;
    }
    if (selectedTemplate) {
      return selectedTemplate.allow_format_switch ?? false;
    }
    return true;
  }, [providerModal.editing, selectedTemplate]);

  const drawerFooter = providerModal.step === 1
    ? (
      <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
        <Button onClick={handleCloseProviderModal}>{t('Cancel')}</Button>
      </Space>
    )
    : (
      <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
        {!providerModal.editing && (
          <Button icon={<ArrowLeftOutlined />} onClick={handleBackToTemplateStep}>
            {t('Back to Templates')}
          </Button>
        )}
        <Button onClick={handleCloseProviderModal}>{t('Cancel')}</Button>
        <Button type="primary" onClick={handleSubmitProvider}>
          {t('Save')}
        </Button>
      </Space>
    );

  return (
    <Space direction="vertical" size={24} style={{ width: '100%' }}>
      <div className="fx-ai-top-bar">
        <div>
          <Title level={3} style={{ marginBottom: 4 }}>{t('AI Providers & Models')}</Title>
          <Text type="secondary">
            {t('Manage AI providers, synchronize compatible models, and configure default capabilities across the system.')}
          </Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => handleOpenProviderModal()}>
          {t('Add Provider')}
        </Button>
      </div>

      <Row gutter={[24, 24]}>
        {providers.map((provider) => (
          <Col key={provider.id} xs={24}>
            {renderProviderCard(provider)}
          </Col>
        ))}
        {!providers.length && !loading ? (
          <Col span={24}>
            <Card className="fx-ai-empty-card">
              <Empty description={t('Add your first AI provider to get started')} />
            </Card>
          </Col>
        ) : null}
      </Row>

      <Card className="fx-ai-defaults-card" title={t('Default Models Configuration')}>
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          {abilityOrder.map((ability) => {
            const info = abilityInfo[ability];
            const options = collectionsByAbility(ability);
            return (
              <div key={ability} className="fx-ai-default-row">
                <div className="fx-ai-default-meta">
                  <div className={`fx-ai-default-icon fx-ai-${ability}`}>
                    {info.icon}
                  </div>
                  <div>
                    <Text strong>{t(info.label)}</Text>
                    <div className="fx-ai-default-desc">{t(info.description)}</div>
                  </div>
                </div>
                <Select
                  allowClear
                  style={{ minWidth: 280 }}
                  placeholder={t('Select a model')}
                  value={defaultSelections[ability] ?? undefined}
                  options={options}
                  onChange={(value) => updateSelection(ability, value ?? null)}
                />
              </div>
            );
          })}
          <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
            <Button type="primary" loading={savingDefaults} onClick={handleSaveDefaults}>
              {t('Save')}
            </Button>
          </Space>
        </Space>
      </Card>

      <Drawer
        width={640}
        open={providerModal.open}
        title={providerModal.editing ? t('Edit Provider') : t('Add Provider')}
        onClose={handleCloseProviderModal}
        footer={drawerFooter}
      >
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          <Steps
            size="small"
            current={providerModal.step - 1}
            items={stepItems}
            className="fx-ai-add-provider-steps"
          />
          {providerModal.step === 1 ? (
            <div className="fx-ai-template-grid">
              {providerTemplates.map((template) => (
                <div
                  key={template.key}
                  className="fx-ai-template-card"
                  role="button"
                  tabIndex={0}
                  onClick={() => handleTemplateSelect(template)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      handleTemplateSelect(template);
                    }
                  }}
                >
                  <div className="fx-ai-template-card-main">
                    <div className="fx-ai-template-icon">
                      {template.logo_url ? (
                        <img src={template.logo_url} alt={t(template.nameKey)} />
                      ) : (
                        <RobotOutlined />
                      )}
                    </div>
                    <div className="fx-ai-template-text">
                      <div className="fx-ai-template-name">{t(template.nameKey)}</div>
                      <div className="fx-ai-template-desc">{t(template.descriptionKey)}</div>
                    </div>
                  </div>
                  <ArrowRightOutlined className="fx-ai-template-arrow" />
                </div>
              ))}
            </div>
          ) : (
            <>
              {activeTemplate ? (
                <div className="fx-ai-template-summary">
                  <div className="fx-ai-template-icon summary">
                    {activeTemplate.logo_url ? (
                      <img src={activeTemplate.logo_url} alt={t(activeTemplate.nameKey)} />
                    ) : (
                      <RobotOutlined />
                    )}
                  </div>
                  <div className="fx-ai-template-summary-text">
                    <div className="fx-ai-template-name">{t(activeTemplate.nameKey)}</div>
                    <div className="fx-ai-template-desc">{t(activeTemplate.descriptionKey)}</div>
                    <Space size={8} wrap>
                      <Tag color="blue">{(providerForm.getFieldValue('api_format') || activeTemplate.api_format).toUpperCase()} API</Tag>
                      {activeTemplate.doc_url ? (
                        <a href={activeTemplate.doc_url} target="_blank" rel="noreferrer">
                          {t('View Docs')}
                        </a>
                      ) : null}
                    </Space>
                  </div>
                </div>
              ) : null}
              <Form layout="vertical" form={providerForm}>
                <Form.Item name="provider_type" hidden>
                  <Input />
                </Form.Item>
                <Form.Item
                  name="name"
                  label={t('Display Name')}
                  rules={[{ required: true, message: t('Enter name') }]}
                >
                  <Input />
                </Form.Item>
                <Form.Item
                  name="identifier"
                  label={t('Identifier')}
                  rules={[
                    { required: true, message: t('Enter identifier') },
                    { pattern: /^[a-z0-9_\-.]+$/, message: t('Only lowercase letters, numbers, dash, dot and underscore are allowed') },
                  ]}
                >
                  <Input disabled={!!providerModal.editing} />
                </Form.Item>
                <Form.Item
                  name="api_format"
                  label={t('API Format')}
                  rules={[{ required: true }]}
                >
                  <Select
                    disabled={!allowFormatChange}
                    options={[
                      { value: 'openai', label: 'OpenAI Compatible' },
                      { value: 'gemini', label: 'Gemini Compatible' },
                    ]}
                  />
                </Form.Item>
                <Form.Item name="base_url" label={t('Base URL')} rules={[{ required: true, message: t('Enter base url') }]}>
                  <Input placeholder="https://" />
                </Form.Item>
                <Form.Item
                  name="api_key"
                  label={(
                    <Space size={8}>
                      {t('API Key')}
                      {providerModal.editing ? (
                        <Tag color={providerModal.editing.has_api_key ? 'green' : 'default'}>
                          {providerModal.editing.has_api_key ? '已设置' : '未设置'}
                        </Tag>
                      ) : null}
                    </Space>
                  )}
                >
                  <Input.Password
                    placeholder={
                      providerModal.editing
                        ? '留空不更新，填写将覆盖'
                        : t('Optional, can also be provided per request')
                    }
                    autoComplete="new-password"
                    visibilityToggle={false}
                  />
                </Form.Item>
                <Form.Item name="logo_url" label={t('Logo URL')}>
                  <Input placeholder="https://" />
                </Form.Item>
              </Form>
            </>
          )}
        </Space>
      </Drawer>

      <Drawer
        width={520}
        open={modelModal.open}
        title={modelModal.editing ? t('Edit Model') : t('Add Model')}
        onClose={handleCloseModelModal}
        footer={(
          <Space style={{ justifyContent: 'flex-end', width: '100%' }}>
            <Button onClick={handleCloseModelModal}>{t('Cancel')}</Button>
            <Button type="primary" onClick={handleSubmitModel} disabled={addingRemoteModels}>
              {t('Save')}
            </Button>
          </Space>
        )}
      >
        <Space direction="vertical" size={24} style={{ width: '100%' }}>
          {modelModal.editing ? (
            renderManualModelForm()
          ) : (
            <Tabs
              activeKey={modelModalTab}
              onChange={(key) => setModelModalTab(key as 'remote' | 'manual')}
              destroyInactiveTabPane={false}
              style={{ width: '100%' }}
              items={[
                {
                  key: 'remote',
                  label: t('Pull Models'),
                  children: renderRemoteModelsTab(),
                },
                {
                  key: 'manual',
                  label: t('Manual Add'),
                  children: renderManualModelForm(),
                },
              ]}
            />
          )}
        </Space>
      </Drawer>
    </Space>
  );
}
