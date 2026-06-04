import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from attendance_system.config import load_config, get_config
from attendance_system.models import PunchRecord, AnomalyRecord, DashboardMetric
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, func

async def check_data():
    load_config()
    cfg = get_config()
    print(f'数据库: {cfg.database.url}')
    
    engine = create_async_engine(cfg.database.url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        punch_count = (await session.execute(select(func.count()).select_from(PunchRecord))).scalar()
        anomaly_count = (await session.execute(select(func.count()).select_from(AnomalyRecord))).scalar()
        metric_count = (await session.execute(select(func.count()).select_from(DashboardMetric))).scalar()
        
        print(f'打卡记录数: {punch_count}')
        print(f'异常记录数: {anomaly_count}')
        print(f'Dashboard统计数: {metric_count}')
        
        if punch_count == 0:
            print('\n⚠️  没有打卡数据！需要重新生成。')
    
    await engine.dispose()

if __name__ == '__main__':
    asyncio.run(check_data())
