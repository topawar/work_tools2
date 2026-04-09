-- 批量导入 SQL 文件
-- 表单：合同明细单价修改
-- 生成时间：2026-04-07 16:10:45
-- 总行数：1，成功：1，失败：0

-- ==================== 第 2 行数据 ====================

-- 执行语句
UPDATE t1
SET qty = '3',
  price = '5',
  taxrate = '7',
  status = '9',
  TYPE = '11',
  name = '13', date = '15',
  address = '17',
  contact = '21'
  WHERE itemid = '1'
  AND bpolineid = '2'

UPDATE t2
SET qty = '3',
  price = '5',
  taxrate = '7',
  status = '9',
  name = '13', date = '15',
  address = '17',
  contact = '21'
  WHERE itemid = '1'
  AND bpolineid = '2'

UPDATE t3
SET qty = '3',
  price = '5',
  taxrate = '7',
  name = '13', date = '15',
  address = '17',
  contact = '21'
  WHERE itemid = '1'
  AND bpolineid = '2'

-- 回退语句
UPDATE t1
SET qty = '4',
  price = '6',
  taxrate = '8',
  status = '10',
  TYPE = '12',
  name = '14', date = '16',
  address = '18',
  address_district = '19',
  address_street = '20',
  contact = '22',
  contact_area_code = '23',
  contact_extension = '24'
  WHERE itemid = '1'
  AND bpolineid = '2'

UPDATE t2
SET qty = '4',
  price = '6',
  taxrate = '8',
  status = '10',
  name = '14', date = '16',
  address = '18',
  address_district = '19',
  address_street = '20',
  contact = '22',
  contact_area_code = '23',
  contact_extension = '24'
  WHERE itemid = '1'
  AND bpolineid = '2'

UPDATE t3
SET qty = '4',
  price = '6',
  taxrate = '8',
  name = '14', date = '16',
  address = '18',
  address_district = '19',
  address_street = '20',
  contact = '22',
  contact_area_code = '23',
  contact_extension = '24'
  WHERE itemid = '1'
  AND bpolineid = '2'
