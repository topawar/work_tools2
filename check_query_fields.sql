-- 检查表单配置ID=1的查询字段默认值
SELECT 
    id,
    label,
    binding_key,
    default_value,
    valid_rule,
    sort_order
FROM work_tools2_formqueryitem
WHERE form_config_id = 1
ORDER BY sort_order;
