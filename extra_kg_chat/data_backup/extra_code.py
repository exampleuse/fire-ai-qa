import json
import re
import concurrent.futures
from tqdm import tqdm
from http import HTTPStatus
import dashscope

 
PROMPT = '''
# 背景
你是一个信息抽取专家
# 任务
可以根据一段文本，抽取该段话的实体和关系，并形成三元组形式
# 数据结构设计
{label_json}
# 要求
1 尽可能抽取准确,必须从文本中抽取相关信息，不能随意发挥
2 不要抽取和数据结构设计之外的数据类型和关系类型
3 必须选择数据结构设计列表中的一个{"start_label": "xxx", "rel": "xxx", "end_label": "xx"},并抽取的实体变成
{"start_label": "xxx","start_entity":'xxx', "rel": "xxx", "end_label": "xx","end_entity":"xxx"}
# 示例
输入：

输出：
[{"start_label": "xxx","start_entity":'xxx', "rel": "xxx", "end_label": "xx","end_entity":"xxx"},....]

'''


def get_data_list(text):
    '''
    数据处理
    :param text:
    :return:
    '''
    try:
        data_dict = json.loads(text)
    except:
        try:
            data_dict = eval(text)
        except:
            try:
                result = re.findall(r'\[(.*?)\]', text.replace('\n', ''))
                if result and len(result) == 1:
                    data_dict = eval('[' + result[0] + ']')
                else:
                    data_dict = []
            except:
                data_dict = []
    return data_dict


label_list = []



with open('cache.json', 'r', encoding='utf-8') as f:
    data_dict = json.load(f)


def llm_extra(text):
    '''
    qwen大模型
    :param text:
    :param prompt:
    :return:
    '''
    with open('label.json', 'r', encoding='utf-8') as f:
        label_list = json.load(f)
    dashscope.api_key = ''
    if text in data_dict:
        return data_dict[text], text
    messages = [{'role': 'system', 'content': PROMPT.replace('{label_json}', str(label_list))},
                {'role': 'user', 'content': text}]
    try:
        response = dashscope.Generation.call(
            "deepseek-v3",
            messages=messages,
            result_format='message',  # set the result to be "message" format.
        )
    except:
        print('调用qwen模型失败')
        return '', text
    if response.status_code == HTTPStatus.OK:
        data_dict[text] = response['output']['choices'][0]['message']['content']
        with open('cache.json', 'w', encoding='utf-8') as f:
            f.write(json.dumps(data_dict, ensure_ascii=False))
        return response['output']['choices'][0]['message']['content'], text
    else:
        print('Request id: %s, Status code: %s, error code: %s, error message: %s' % (
            response.request_id, response.status_code,
            response.code, response.message
        ))
        return '', text


def code_(data_list):
    '''
    多线程调用大模型
    '''
    total_list = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(llm_extra, data) for data in data_list]
        for future in tqdm(concurrent.futures.as_completed(futures)):
            try:
                result, text = future.result()
                result_list = get_data_list(result)
                if result_list:
                    total_list.append({'content': text, 'result': result_list})
                    with open('result.json', 'w', encoding='utf-8') as f:
                        f.write(json.dumps(total_list, ensure_ascii=False))
                    f.close()
            except Exception as e:
                print(f"An error occurred: {e}")

    with open('result.json', 'w', encoding='utf-8') as f:
        f.write(json.dumps(total_list, ensure_ascii=False,indent=4))
    f.close()
    return total_list




def main():
    '''
    主流程
    '''
    content = ''
    with open('input.txt','r',encoding='utf-8') as f:
        for lin in f:
            content += lin
    txt_list = [content[i:i + 1000] for i in range(0, len(content), 1000)]
    code_(txt_list)


if __name__ == '__main__':
    main()
