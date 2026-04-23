import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal, engine
import models
import auth_utils

def seed_db():
    print("--- Database Reset Started ---")
    
    # DROP and CREATE tables to ensure association tables (batch_students, etc.) are empty
    # This is the most reliable way to fix IntegrityErrors during local testing.
    models.Base.metadata.drop_all(bind=engine)
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    
    try:
        print("Seeding Users...")
        # 1. Create Institution
        inst_user = models.User(
            name="Alpha Institution", 
            email="alpha@inst.com", 
            hashed_password=auth_utils.hash_password("password"), 
            role="institution"
        )
        db.add(inst_user)
        
        # 2. Create Government Monitoring Officer
        gov_user = models.User(
            name="Officer Smith", 
            email="officer@gov.com", 
            hashed_password=auth_utils.hash_password("password"), 
            role="monitoring_officer"
        )
        db.add(gov_user)

        # 3. Create Trainers
        trainer_list = []
        for i in range(3):
            trainer = models.User(
                name=f"Trainer {i}", 
                email=f"trainer{i}@test.com", 
                hashed_password=auth_utils.hash_password("password"), 
                role="trainer"
            )
            db.add(trainer)
            trainer_list.append(trainer)

        # 4. Create Students
        student_list = []
        for i in range(15):
            student = models.User(
                name=f"Student {i}", 
                email=f"student{i}@test.com", 
                hashed_password=auth_utils.hash_password("password"), 
                role="student"
            )
            db.add(student)
            student_list.append(student)
        
        # Commit users first so IDs are generated
        db.commit()

        print("Seeding Batches...")
        # 5. Create Batches and link trainers/students via relationships
        batches_created = []
        for i in range(3):
            new_batch = models.Batch(
                name=f"Robotics Batch {i+1}", 
                institution_id=inst_user.id
            )
            
            # Associate one trainer with this batch
            new_batch.trainers.append(trainer_list[i])
            
            # Associate 5 students with this batch
            start_idx = i * 5
            end_idx = start_idx + 5
            for student in student_list[start_idx:end_idx]:
                new_batch.students.append(student)
                
            db.add(new_batch)
            batches_created.append(new_batch)
        
        db.commit()

        print("Seeding Attendance Records...")
        # 6. Create Attendance for the Monitoring Officer
        today = datetime.date.today()
        for i, student in enumerate(student_list):
            # Map student to the correct batch (0-4 -> Batch 1, 5-9 -> Batch 2, etc.)
            target_batch = batches_created[i // 5]
            
            status = "present" if i % 3 != 0 else "absent"
            
            attendance_record = models.Attendance(
                student_id=student.id,
                session_id=target_batch.id,
                status=status,
                marked_at=today - datetime.timedelta(days=(i % 2))
            )
            db.add(attendance_record)

        db.commit()
        print("--- Database Seeded Successfully! ---")

    except Exception as e:
        print(f"!!! Error during seeding: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()