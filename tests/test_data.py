import io
import uuid
import pandas as pd
import pytest
from framework import data
from framework.config import ALWAYS_LOAD_COLUMNS
from framework.analysis import aggregate, chronological_order, filter_range, filter_values, transitions, reduce_points

@pytest.fixture(autouse=True)
def private_root(tmp_path, monkeypatch):
    monkeypatch.setattr(data, 'ROOT', tmp_path)

def source(text, session=None):
    return data.save_source(io.BytesIO(text.encode()), session or str(uuid.uuid4()))

def test_sample_regression():
    frame = data.load_projection('synthetic_sales_data.csv', ALWAYS_LOAD_COLUMNS)
    with open('synthetic_sales_data.csv', 'rb') as sample:
        while sample.peek(1).startswith(b'%'):
            sample.readline()
        expected = pd.read_csv(sample)
    expected['Date'] = pd.to_datetime(expected.Date, dayfirst=True)
    expected = expected.sort_values('Date', kind='stable').reset_index(drop=True)
    pd.testing.assert_frame_equal(frame, expected)


@pytest.mark.parametrize('newline', ['\n', '\r\n', '\r'])
def test_stamped_source_matches_clean_source(newline):
    csv_text = '"%Label",Seconds,value\n"%row",2,"one\n%still data"\nlast,1,\n'
    stamp = ('% café END TIME: 19:20:54.22 before version: 1.5, extra text\n'
             '%% unknown "quotes\n%% version: 9.9\n'
             '% start time: 18:00:30.35\n%\n')
    clean = source(csv_text.replace('\n', newline))
    path, header = data.stage_source(
        io.BytesIO(('\ufeff' + stamp + csv_text).replace('\n', newline).encode('utf-8')),
        str(uuid.uuid4()),
    )
    assert header.preamble.entries == ('END TIME: 19:20:54.22', 'Elapsed time: 01:20:23.87',
                                       'version: 1.5', 'start time: 18:00:30.35')
    columns = ['%Label', 'Seconds', 'value']
    assert data.inspect_header(path) == columns
    assert data.inspect_numeric_range(path) == data.inspect_numeric_range(clean)
    for seconds_range in [None, (2, 2)]:
        expected = data.load_projection(clean, columns, seconds_range=seconds_range)
        for _ in range(2):  # The second load can use the private Parquet projection.
            active = data.load_dataset(path, 'stamped.csv', columns, True, seconds_range, header)
            assert active.header is header
            pd.testing.assert_frame_equal(active.frame, expected)
    assert expected['value'].tolist() == ['one' + newline + '%still data']


@pytest.mark.parametrize('row', ['one,2,3', '"unterminated'])
def test_stamped_validation_reports_original_line(row):
    with pytest.raises(ValueError, match='line 5'):
        source(f'% version: 1.5\r\n%\r\n"a\r\nb",c\r\n{row}\r\n')


def test_stamp_without_column_header_is_invalid():
    with pytest.raises(ValueError, match='requires one header row'):
        source('% version: 1.5\n%')


@pytest.mark.parametrize('stamp, expected', [
    ('% start time: 23:59:59.95\n% end time: 00:00:00.20\n', '00:00:00.25'),
    ('% start time: 08:00:00.00\n% end time: 08:00:00.00\n', '00:00:00.00'),
    ('% start time: 08:00:00.00\n', None),
    ('% start time: 99:00:00.00\n% end time: 08:00:00.00\n', None),
])
def test_stamp_elapsed_time(stamp, expected):
    header = data.inspect_source(source(stamp + 'Seconds\n0\n'))
    elapsed = [entry for entry in header.preamble.entries if entry.startswith('Elapsed time:')]
    assert elapsed == ([f'Elapsed time: {expected}'] if expected is not None else [])

def test_projection_and_add_columns():
    path = source('time,state,speed,other\n0,on,3,x\n1,off,4,y\n')
    assert list(data.load_projection(path, ['time']).columns) == ['time']
    assert list(data.load_projection(path, ['time', 'speed']).columns) == ['time', 'speed']
    assert data.load_projection(path, ['speed']).speed.tolist() == [3, 4]

def test_seconds_profile_and_inclusive_projection():
    path = source('Seconds,value\n0,a\n0.5,b\nbad,c\n1.5,d\n2,e\n')
    profile = data.inspect_numeric_range(path)
    assert (profile.minimum, profile.maximum, profile.step) == (0, 2, 0.5)
    assert (profile.valid_rows, profile.invalid_rows) == (4, 1)
    frame = data.load_projection(path, ['Seconds', 'value'], seconds_range=(0.5, 1.5))
    # Filtering coerces a temporary comparison series while preserving source dtype.
    assert frame.Seconds.tolist() == ['0.5', '1.5']
    assert frame.value.tolist() == ['b', 'd']

def test_seconds_filter_works_when_seconds_is_not_selected():
    path = source('Seconds,value\n0,a\n1,b\n2,c\n')
    frame = data.load_projection(path, ['value'], seconds_range=(1, 2))
    assert list(frame) == ['value']
    assert frame.value.tolist() == ['b', 'c']

def test_seconds_profile_requires_a_numeric_value():
    path = source('Seconds,value\ninvalid,a\n,b\n')
    with pytest.raises(ValueError, match='no numeric values'):
        data.inspect_numeric_range(path)

def test_isolation_and_cleanup():
    a = source('time,x\n0,1\n')
    b = source('time,x\n0,2\n')
    assert a.parent != b.parent
    assert data.load_dataset(a, 'same.csv', ['x']).frame.x.iloc[0] == 1
    assert data.load_dataset(b, 'same.csv', ['x']).frame.x.iloc[0] == 2
    data.cleanup(now=a.parent.stat().st_mtime + data.TTL_SECONDS + 2)
    assert not a.exists() and not b.exists()

@pytest.mark.parametrize('text', ['', 'a,a\n1,2\n', 'a,\n1,2\n'])
def test_bad_headers(text):
    with pytest.raises(ValueError): source(text)

def test_invalid_uuid():
    with pytest.raises(ValueError): source('a\n1', '../escape')

def test_limits(monkeypatch):
    monkeypatch.setattr(data, 'MAX_FRAME_MB', 0)
    with pytest.raises(ValueError, match='fewer columns'):
        data.load_projection(source('a\n1'), ['a'])
    monkeypatch.setattr(data, 'MAX_UPLOAD_MB', 0)
    with pytest.raises(ValueError, match='Upload exceeds'):
        source('a\n1')

def test_parquet_equivalence_and_fallback(monkeypatch):
    path = source('time,state,speed\n2,on,1.5\n1,,\n0,off,3\n')
    expected = data.load_projection(path, ['time', 'state', 'speed'])
    pd.testing.assert_frame_equal(expected, data.load_projection(path, list(expected), True))
    pd.testing.assert_frame_equal(expected, data.load_projection(path, list(expected), True))
    for cache in path.parent.glob('*.parquet'): cache.write_bytes(b'broken')
    pd.testing.assert_frame_equal(expected, data.load_projection(path, list(expected), True))

def test_operations():
    frame = pd.DataFrame({'time': [0,1,2,3], 'state': ['a','a','b','b'], 'v':[1,2,3,4]})
    assert filter_range(frame, 'v', 2, 3).v.tolist() == [2,3]
    assert filter_values(frame, 'state', ['a']).v.tolist() == [1,2]
    assert aggregate(frame, ['state'], 'v', 'sum').v.tolist() == [3,7]
    assert transitions(frame, ['state']).time.tolist() == [0,2]
    assert reduce_points(frame, 2).time.tolist() == [0,3]
    nulls = pd.DataFrame({'a':[None,None,1,1]})
    assert transitions(nulls, ['a']).index.tolist() == [0,2]


def test_chronological_order_is_stable_and_supports_seconds_tiebreaking():
    frame = pd.DataFrame(
        {
            'Date': ['02/01/2024', '01/01/2024', '01/01/2024'],
            'Seconds': [2.0, 1.0, 0.5],
            'value': ['later', 'second', 'first'],
        },
        index=[20, 10, 5],
    )
    ordered = chronological_order(frame, 'Date', secondary='Seconds')
    assert ordered.value.tolist() == ['first', 'second', 'later']
    assert ordered.index.tolist() == [5, 10, 20]
    assert chronological_order(frame, 'Seconds', numeric=True).Seconds.tolist() == [0.5, 1.0, 2.0]

@pytest.mark.parametrize('text', ['a,b\n1,2,3\n', 'a,b\n1\n', 'a,b\n"unclosed,2\n'])
def test_malformed_rows(text):
    import csv
    with pytest.raises((ValueError, csv.Error)):
        source(text)
