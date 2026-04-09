-- 表单：合同明细单价修改
-- 生成时间：2026-04-07 16:27:19
-- 文件名：1_2_3

-- ==================== 执行语句 ====================

-- 执行语句 1
UPDATE t1
SET qty = qty,
  price = price,
  taxrate = taxrate,
  status = 'active',
  TYPE = 'true',
  name = '2344', date = '20260507',
  address = '北京市朝阳区',
  address_district = '朝阳区',
  address_street = '建国路',
  contact = '010-1234',
  contact_area_code = '010',
  contact_extension = '1234'
  WHERE bpolineid = '23'

-- 执行语句 2
UPDATE t2
SET qty = qty,
  price = price,
  taxrate = taxrate,
  status = 'active',
  name = '2344', date = '20260507',
  address = '北京市朝阳区',
  address_district = '朝阳区',
  address_street = '建国路',
  contact = '010-1234',
  contact_area_code = '010',
  contact_extension = '1234'
  WHERE bpolineid = '23'

-- 执行语句 3
UPDATE t3
SET qty = qty,
  price = price,
  taxrate = taxrate,
  name = '2344', date = '20260507',
  address = '北京市朝阳区',
  address_district = '朝阳区',
  address_street = '建国路',
  contact = '010-1234',
  contact_area_code = '010',
  contact_extension = '1234'
  WHERE bpolineid = '23'

-- ==================== 回退语句 ====================

-- 回退语句 1
UPDATE t1
SET qty = '100',
  price = '50.00',
  taxrate = '0.13',
  status = 'active',
  TYPE = 'False',
  name = '张三', date = '20240101',
  address = '北京市朝阳区',
  address_district = '朝阳区',
  address_street = '建国路',
  contact = '010-1234',
  contact_area_code = '010',
  contact_extension = '1234'
  WHERE bpolineid = '23'

-- 回退语句 2
UPDATE t2
SET qty = '100',
  price = '50.00',
  taxrate = '0.13',
  status = 'active',
  name = '张三', date = '20240101',
  address = '北京市朝阳区',
  address_district = '朝阳区',
  address_street = '建国路',
  contact = '010-1234',
  contact_area_code = '010',
  contact_extension = '1234'
  WHERE bpolineid = '23'

-- 回退语句 3
UPDATE t3
SET qty = '100',
  price = '50.00',
  taxrate = '0.13',
  name = '张三', date = '20240101',
  address = '北京市朝阳区',
  address_district = '朝阳区',
  address_street = '建国路',
  contact = '010-1234',
  contact_area_code = '010',
  contact_extension = '1234'
  WHERE bpolineid = '23'
