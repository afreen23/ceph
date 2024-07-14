import { ComponentFixture, TestBed } from '@angular/core/testing';

import { NvmeofNamespacesFormComponent } from './nvmeof-namespaces-form.component';

describe('NvmeofNamespacesFormComponent', () => {
  let component: NvmeofNamespacesFormComponent;
  let fixture: ComponentFixture<NvmeofNamespacesFormComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [NvmeofNamespacesFormComponent]
    }).compileComponents();

    fixture = TestBed.createComponent(NvmeofNamespacesFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
